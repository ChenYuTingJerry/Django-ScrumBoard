from rest_framework import viewsets, authentication, permissions, filters
from rest_framework.renderers import JSONRenderer
from django_filters.rest_framework import DjangoFilterBackend
from django.core.signing import TimestampSigner
from django.contrib.auth import get_user_model
from django.conf import settings

from .forms import TaskFilter, SprintFilter
from .models import Sprint, Task
from .serializers import SprintSerializer, TaskSerializer, UserSerializer
import requests
import hashlib

User = get_user_model()


class DefaultsMixin(object):
    """Default settings for view authentication, permissions,
    filtering and pagination."""

    authentication_classes = (
        authentication.BasicAuthentication,
        authentication.TokenAuthentication,
    )
    permission_classes = (
        permissions.IsAuthenticated,
    )
    paginate_by = 25
    paginate_by_param = 'page_size'
    max_paginate_by = 100
    filter_backends = (
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    )


class UpdateHookMixin(object):
    """Mixin class to send update information to the websocket server."""

    def _build_hook_url(self, obj):
        if isinstance(obj, User):
            model = 'user'
        else:
            model = obj.__class__.__name__.lower()
        return '{}://{}/{}/{}'.format(
            'https' if settings.WATERCOOLER_SECURE else 'http',
            settings.WATERCOOLER_SERVER, model, obj.pk)

    def _send_hook_request(self, obj, method):
        url = self._build_hook_url(obj)
        if method in ('POST', 'PUT'):
            # Build the body
            serializer = self.get_serializer(obj)
            renderer = JSONRenderer()
            context = {'request': self.request}
            body = renderer.render(serializer.data, renderer_context=context)
        else:
            body = None
        headers = {
            'content-type': 'application/json',
            'X-Signature': self._build_hook_signature(method, url, body)
        }
        try:
            response = requests.request(method, url, data=body, timeout=0.5, headers=headers)
            response.raise_for_status()
        except requests.exceptions.ConnectionError:
            # Host could not be resolved or the connection was refused
            pass
        except requests.exceptions.Timeout:
            # Request time out
            pass
        except requests.exceptions.RequestException:
            # Server responses with 4xx or 5xx status code
            pass

    def _build_hook_signature(self, method, url, body):
        signer = TimestampSigner(settings.WATERCOOLER_SECRET)
        value = '{method}:{url}:{body}'.format(
            method=method.lower(),
            url=url,
            body=hashlib.sha256(body or b'').hexdigest()
        )
        return signer.sign(value)

    def perform_create(self, serializer):
        super(UpdateHookMixin, self).perform_create(serializer)
        self._send_hook_request(serializer.instance, 'POST')

    def perform_update(self, serializer):
        super(UpdateHookMixin, self).perform_update(serializer)
        self._send_hook_request(serializer.instance, 'PUT')

    def perform_destroy(self, instance):
        self._send_hook_request(instance, 'DELETE')
        super(UpdateHookMixin, self).perform_destroy(instance)


class SprintViewSet(DefaultsMixin, UpdateHookMixin, viewsets.ModelViewSet):
    """API endpoint for listing and creating sprints."""
    queryset = Sprint.objects.order_by('end')
    serializer_class = SprintSerializer
    filter_class = SprintFilter
    search_fields = ('name',)
    ordering_fields = ('end', 'name',)


class TaskViewSet(DefaultsMixin, UpdateHookMixin, viewsets.ModelViewSet):
    """API endpoint for listing and creating tasks."""
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    filter_class = TaskFilter
    search_fields = ('name', 'description',)
    ordering_fields = ('name', 'order', 'started', 'due', 'completed',)


class UserViewSet(DefaultsMixin, UpdateHookMixin, viewsets.ReadOnlyModelViewSet):
    """API endpoint for listing users."""
    lookup_field = User.USERNAME_FIELD
    lookup_url_kwarg = User.USERNAME_FIELD
    queryset = User.objects.order_by(User.USERNAME_FIELD)
    serializer_class = UserSerializer
    search_fields = (User.USERNAME_FIELD,)
