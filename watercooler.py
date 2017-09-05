from urllib.parse import urlparse
from tornado.ioloop import IOLoop
from tornado.options import define, parse_command_line, options
from tornado.web import Application
from tornado.websocket import WebSocketHandler, WebSocketClosedError
from tornado.httpserver import HTTPServer
from collections import defaultdict
import logging
import signal
import time

define('debug', default=False, type=bool, help='Run in debug mode')
define('port', default=8080, type=int, help='Server port')
define('allowed_hosts', default='localhost:8080', multiple=True,
       help='Allowed hosts for cross domain connections')


class SprintHandler(WebSocketHandler):
    """ Handles real-time updates to the board. """

    def data_received(self, chunk):
        pass

    def check_origin(self, origin):
        allowed = super(SprintHandler, self).check_origin(origin)
        parsed = urlparse(origin.lower())
        matched = any(parsed.netloc == host for host in options.allowed_hosts)
        return options.debug or allowed or matched

    def open(self, sprint):
        """ Subscribe to sprint updates on a new connection. """
        self.sprint = sprint
        self.application.add_subscriber(self.sprint, self)

    def on_message(self, message):
        """ Broadcast updates to other interested clients. """
        self.application.broadcast(message, channel=self.sprint, sender=self)

    def on_close(self):
        """ Remove subscription. """
        self.application.remove_subscriber(self.sprint, self)


class ScrumApplication(Application):
    def __init__(self, **kwargs):
        routes = [
            (r'/(?P<sprint>[0-9]+)', SprintHandler),
        ]
        super(ScrumApplication, self).__init__(routes, **kwargs)
        self.subscriptions = defaultdict(list)

    def add_subscriber(self, channel, subscriber):
        print('add_subscriber')
        self.subscriptions[channel].append(subscriber)

    def remove_subscriber(self, channel, subscriber):
        print('remove_subscriber')
        self.subscriptions[channel].remove(subscriber)

    def get_subscriber(self, channel):
        print('get_subscriber: {}'.format(channel))
        return self.subscriptions[channel]

    def broadcast(self, message, channel=None, sender=None):
        print('broadcast: {}'.format(self.subscriptions))
        if channel is None:
            print('----- ooooooo ------')
            for c in self.subscriptions.keys():
                self.broadcast(message, channel=c, sender=sender)
        else:
            print('----- xxxxxxx ------')
            peers = self.get_subscriber(channel)
            for peer in peers:
                if peer != sender:
                    try:
                        peer.write_message(message)
                    except WebSocketClosedError:
                        self.remove_subscriber(channel, peer)


def shutdown(server):
    ioloop = IOLoop.current(instance=True)
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
    IOLoop.current(instance=True).start()
