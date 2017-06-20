import logging

from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.filters import DjangoObjectPermissionsFilter

import accounts.serializers as serializers
from accounts.permissions import UserObjectPermissions
from accounts.filters import UserObjectPermissionsFilter

logger = logging.getLogger(__name__)


class UsersView(generics.ListAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer
    permission_classes = (UserObjectPermissions,)
    filter_backends = (UserObjectPermissionsFilter,)


class UserView(generics.RetrieveAPIView):
    lookup_field = 'id'
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer
    permission_classes = (UserObjectPermissions,)
    filter_backends = (UserObjectPermissionsFilter,)

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'me':
            self.kwargs[lookup_url_kwarg] = self.request.user.id
        return super(UserView, self).get_object()


class UserProfilesView(generics.ListAPIView):
    lookup_field = 'id'
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer
    permission_classes = (UserObjectPermissions,)
    filter_backends = (UserObjectPermissionsFilter,)

    def get_queryset(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'me':
            self.kwargs[lookup_url_kwarg] = self.request.user.id

        user = self.request.user
        queryset = user.act_as_profiles.all()
        return queryset
