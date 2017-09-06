(function ($, Backbone, _, app) {

    function csrfSafeMethod(method) {
        return (/^(GET|HEAD|OPTIONS|TRACE)$/i.test(method));
    }

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = $.trim(cookies[i]);
                if (cookie.substring(0, name.length + 1) == (name + '=')) {
                    cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    $.ajaxPrefilter(function (settings, originalOptions, xhr) {
        var csrftoken;
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            csrftoken = getCookie('csrftoken');
            xhr.setRequestHeader('X-CSRFToken', csrftoken);
        }
    });

    var Session = Backbone.Model.extend({
            defaults: {
            token: null
        },
        initialize: function (options) {
            this.options = options;
            $.ajaxPrefilter($.proxy(this._setupAuth, this));
            this.load();
        },
        load: function () {
            var token = localStorage.apiToken;
            if (token) {
                this.set('token', token);
            }
        },
        save: function (token) {
            this.set('token', token);
            if (token === null) {
                localStorage.removeItem('apiToken');
            } else {
                localStorage.apiToken = token;
            }
        },
        delete: function () {
            this.save(null);
        },
        authenticated: function () {
            return this.get('token') !== null;
        },
        _setupAuth: function (settings, originalOptions, xhr) {
            if (this.authenticated()) {
                xhr.setRequestHeader(
                    'Authorization',
                    'Token ' + this.get('token')
                );
            }
        }
    });

    app.session = new Session();

    var BaseModel = Backbone.Model.extend({
        url: function (){
            var links = this.get('links');
            var url = links && links.self;
            if(!url){
                url = Backbone.Model.prototype.url.call(this);
            }
            return url;
        }
    });

    app.models.Sprint = BaseModel.extend({
        fetchTasks: function () {
            var links = this.get('links');
            if (links && links.tasks) {
                app.tasks.fetch({
                    url: links.tasks,
                    remove: false
                });
            }
        }
    });
    app.models.Task = BaseModel.extend({
        statusClass: function () {
            var sprint = this.get('sprint');
            var status;
            if (!sprint) {
                status =  'unassigned';
            }else{
                status = ['todo', 'active', 'testing', 'done'][this.get('status') - 1];
            }
            return status;
        },
        inBacklog: function () {
            return !this.get('sprint');
        },
        inSprint: function (sprint) {
            return sprint.get('id') == this.get('sprint');
        },
        moveTo: function(status, sprint, order){
            var updates = {
                status: status,
                sprint: sprint,
                order: order
            };
            var today = new Date().toISOString().replace(/T.*/g, '');
            // Backlog Tasks
            if(!updates.sprint){
                // Tasks move back to the backlog
                updates.stats = 1;
            }
            // Started Tasks
            if((updates.status === 2) || (updates.status > 2 && !this.get('started'))){
                updates.started = today;
            } else if(updates.status < 2 && this.get('started')){
                updates.started = null;
            }
            // Completed Tasks
            if(updates.status === 4){
                updates.completed = today;
            } else if(updates.status < 4 && this.get('completed')){
                updates.completed = null;
            }
            this.save(updates);
        }
    });
    app.models.User = BaseModel.extend({
        idAttributemodel: 'username',
    });

    var BaseCollection = Backbone.Collection.extend({
        parse: function(response){
            this._next = response.next;
            this._previous = response.previous;
            this._count = response.count;
            return response.results || [];
        },
        getOrFetch: function (id) {
            console.log('id: ', id);
            var result = new $.Deferred();
            var model = this.get(id);
            if (!model) {
                model = this.push({id: id});

                model.fetch({
                    success: function (model, response, options) {
                        result.resolve(model);
                    },
                    error: function (model, response, options) {
                        result.reject(model, response);
                    }
                });
            } else {
                result.resolve(model);
            }
            return result;
        }
    });

    app.collections.ready = $.getJSON(app.apiRoot);
    app.collections.ready.done(function (data){
        app.collections.Sprints = BaseCollection.extend({
            model: app.models.Sprint,
            url: data.sprints
        });
        app.sprints = new app.collections.Sprints();
        app.collections.Tasks = BaseCollection.extend({
            model: app.models.Task,
            url: data.tasks,
            getBacklog: function () {
                this.fetch({
                    remove: false,
                    data: {
                        backlog: 'True'
                    }
                });
            }
        });
        app.tasks = new app.collections.Tasks();
        app.collections.Users = BaseCollection.extend({
            model: app.models.User,
            url: data.users
        });
        app.users = new app.collections.Users();
    });

})(jQuery, Backbone, _, app);