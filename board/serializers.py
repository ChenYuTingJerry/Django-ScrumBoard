from datetime import date
from rest_framework import serializers
from .models import Sprint, Task
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.reverse import reverse

User = get_user_model()


class SprintSerializer(serializers.ModelSerializer):
    links = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = ('id', 'name', 'description', 'end', 'links',)

    def get_links(self, obj):
        request = self.context['request']
        return {
            'self': reverse('sprint-detail', kwargs={'pk': obj.pk}, request=request),
            'tasks': reverse('task-list', request=request) + '?sprint={}'.format(obj.pk),
            'channel': '{proto}://{server}/{channel}'.format(
                proto='wss' if settings.WATERCOOLER_SECURE else 'ws',
                server=settings.WATERCOOLER_SERVER,
                channel=obj.pk
            ),
        }

    def validate_end(self, value):
        new = self.instance is None
        changed = self.instance and self.instance.end != value
        if (new or changed) and (value < date.today()):
            msg = _('End date cannot be in the past.')
            raise serializers.ValidationError(msg)
        return value


class TaskSerializer(serializers.ModelSerializer):
    # Relational field must provide a `queryset` argument, override `get_queryset`, or set read_only=`True`.
    # assigned = serializers.SlugRelatedField(slug_field=User.USERNAME_FIELD, required=False, read_only=True)
    assigned = serializers.SlugRelatedField(slug_field=User.USERNAME_FIELD, required=False, allow_null=True,
                                            queryset=User.objects.all())
    status_display = serializers.SerializerMethodField()
    links = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ('id', 'name', 'description', 'sprint', 'status',
                  'order', 'assigned', 'started', 'due', 'completed', 'status_display', 'links')

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_links(self, obj):
        request = self.context['request']
        links = {'self': reverse('task-detail',
                                 kwargs={'pk': obj.pk},
                                 request=request), }
        if obj.sprint_id:
            links['sprint'] = reverse('sprint-detail',
                                      kwargs={'pk': obj.sprint_id},
                                      request=request)
        if obj.assigned:
            links['assigned'] = reverse('user-detail',
                                        kwargs={User.USERNAME_FIELD: obj.assigned},
                                        request=request)
        return links


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    links = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', User.USERNAME_FIELD, 'full_name', 'is_active',
                  'links',)

    def get_links(self, obj):
        request = self.context['request']
        username = obj.get_username()
        return {
            'self': reverse('user-detail',
                            kwargs={User.USERNAME_FIELD: username},
                            request=request),
            'tasks': '{}?assigned={}'.format(reverse('task-list', request=request), username)
        }
