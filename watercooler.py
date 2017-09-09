from urllib.parse import urlparse

from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils.crypto import constant_time_compare
from tornado.ioloop import IOLoop
from tornado.options import define, parse_command_line, options
from tornado.web import Application, RequestHandler, HTTPError
from tornado.websocket import WebSocketHandler, WebSocketClosedError
from tornado.httpserver import HTTPServer
from tornadoredis.pubsub import BaseSubscriber
from tornadoredis import Client
from redis import Redis
import logging
import signal
import time
import uuid
import os
import hashlib
import json

define('debug', default=True, type=bool, help='Run in debug mode')
define('port', default=8080, type=int, help='Server port')
define('allowed_hosts', default='localhost:8000', multiple=True,
       help='Allowed hosts for cross domain connections')


class RedisSubscriber(BaseSubscriber):
    def on_message(self, msg):
        """ Handle new message on Redis channel. """
        if msg and msg.kind == 'message':
            try:
                message = json.loads(msg.body)
                sender = message['sender']
                message = message['message']
            except (ValueError, KeyError):
                message = msg.body
                sender = None
                
            subscribers = list(self.subscribers[msg.channel].keys())
            for subscriber in subscribers:
                if sender is None or sender != subscriber.uid:
                    try:
                        subscriber.write_message(message)
                    except WebSocketClosedError:
                        # Remove dead peer
                        self.unsubscribe(channel_name=msg.channel, subscriber=subscriber)
        super(RedisSubscriber, self).on_message(msg)


class SprintHandler(WebSocketHandler):
    """ Handles real-time updates to the board. """

    def data_received(self, chunk):
        pass

    def check_origin(self, origin):
        print('origin: {}'.format(origin))
        allowed = super(SprintHandler, self).check_origin(origin)
        print('allowed: {}'.format(allowed))
        parsed = urlparse(origin.lower())
        print('parsed: {}'.format(parsed))
        matched = any(parsed.netloc == host for host in options.allowed_hosts)
        print('matched: {}'.format(matched))
        print('options.debug: {}'.format(options.debug))
        return options.debug or allowed or matched

    # def get(self):
    #     print('fuck: {}'.format(self.get_argument('channel', 'fucked')))

    def open(self):
        """ Subscribe to sprint updates on a new connection. """
        print('open')
        self.sprint = None
        channel = self.get_argument('channel', None)
        print('chanel: '+channel)
        if not channel:
            self.close()
        else:
            try:
                self.sprint = self.application.signer.unsign(channel, max_age=60 * 30)
            except (BadSignature, SignatureExpired):
                self.close()
            else:
                self.uid = uuid.uuid4().hex
                print('sprint: {}'.format(self.sprint))
                self.application.add_subscriber(self.sprint, self)

    def on_message(self, message):
        """ Broadcast updates to other interested clients. """
        if self.sprint is not None:
            self.application.broadcast(message, channel=self.sprint, sender=self)

    def on_close(self):
        """ Remove subscription. """
        if self.sprint is not None:
            self.application.remove_subscriber(self.sprint, self)


class UpdateHandler(RequestHandler):
    def data_received(self, chunk):
        pass

    def post(self, model, pk):
        self._broadcast(model, pk, 'add')

    def put(self, model, pk):
        self._broadcast(model, pk, 'update')

    def delete(self, model, pk):
        self._broadcast(model, pk, 'remove')

    def _broadcast(self, model, pk, action):
        signature = self.request.headers.get('X-Signature', None)
        print('signature: '+signature)
        if not signature:
            raise HTTPError(400)
        try:
            result = self.application.signer.unsign(signature, max_age=60 * 1)
        except (BadSignature, SignatureExpired):
            raise HTTPError(400)
        else:
            expected = '{method}:{url}:{body}'.format(
                method=self.request.method.lower(),
                url=self.request.full_url(),
                body=hashlib.sha256(self.request.body).hexdigest(),
            )
            if not constant_time_compare(result, expected):
                raise HTTPError(400)
        try:
            body = json.loads(self.request.body.decode('utf-8'))
        except ValueError:
            body = None
        message = json.dumps({
            'model': model,
            'id': pk,
            'action': action,
            'body': body
        })
        self.application.broadcast(message)
        self.write("Ok")


class ScrumApplication(Application):
    def __init__(self, **kwargs):
        routes = [
            (r'/socket?', SprintHandler),
            (r'/(?P<model>task|sprint|user)/(?P<pk>[0-9]+)', UpdateHandler),
        ]
        super(ScrumApplication, self).__init__(routes, **kwargs)
        print("ScrumApplication")
        self.subscriber = RedisSubscriber(Client())
        self.publisher = Redis()
        self._key = os.environ.get('WATERCOOLER_SECRET', 'pTyz1dzMeVUGrb0Su4QXsP984qTlvQRHpFnnlHuH')
        self.signer = TimestampSigner(self._key)

    def add_subscriber(self, channel, subscriber):
        print('add_subscriber')
        self.subscriber.subscribe(['all', channel], subscriber)

    def remove_subscriber(self, channel, subscriber):
        print('remove_subscriber')
        self.subscriber.unsubscribe(channel, subscriber)
        self.subscriber.unsubscribe('all', subscriber)

    def broadcast(self, message, channel=None, sender=None):
        print('broadcast: {}'.format(message))
        channel = 'all' if channel is None else channel
        message = json.dumps({
            'sender': sender and sender.uid,
            'message': message
        })
        self.publisher.publish(channel, message)


def shutdown(server):
    ioloop = IOLoop.current()
    logging.info('Stopping server.')
    server.stop()

    def finalize():
        ioloop.stop()
        logging.info('Stopped')

    ioloop.add_timeout(time.time() + 0.5, finalize)


if __name__ == "__main__":
    parse_command_line()
    application = ScrumApplication(debug=options.debug)
    server = HTTPServer(application)
    server.listen(options.port)
    signal.signal(signal.SIGINT, lambda sig, frame: shutdown(server))
    logging.info('Starting server on localhost:{}'.format(options.port))
    IOLoop.current().start()
