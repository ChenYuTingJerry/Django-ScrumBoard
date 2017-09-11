(function($, Backbone, _, app){
    var Socket = function(server){
        this.server = server;
        this.ws = null;
        this.connected = new $.Deferred();
        this.open();
    };

    Socket.prototype = _.extend(Socket.prototype, Backbone.Events, {
        open: function(){
            if(this.ws === null){
                this.ws = new WebSocket(this.server);
                this.ws.onopen = $.proxy(this.onopen, this);
                this.ws.onmessage = $.proxy(this.onmessage, this);
                this.ws.onclose = $.proxy(this.onclose, this);
                this.ws.onerror = $.proxy(this.onerror, this);
            }

            return this.connected;
        },
        close: function(){
            if(this.ws && this.ws.close){
                this.ws.close();
            }
            this.ws = null;
            this.connected = new $.Deferred();
            this.trigger('closed');
        },
        onopen: function(){
            this.connected.resolve(true);
            this.trigger('open');
        },
        onmessage: function(message){
            var result = JSON.parse(message.data);
            console.log('onmessage: ',message.data);
            if(result.model && result.action){
                console.log(result.model + ':' + result.action);
                this.trigger(result.model + ':' + result.action, result.id, result, message);
            }
        },
        onclose: function(){
            this.close();
        },
        onerror: function(error){
            this.trigger('error', error);
            this.close();
        },
        send: function(message){
            var self = this;
            var payload = JSON.stringify(message);
            console.log('payload: ', payload);
            this.connected.done(function(){
                self.ws.send(payload);
            });
        }
    });

    app.Socket = Socket;
})(jQuery, Backbone, _, app);