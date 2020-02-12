import csv
import datetime
import logging

import pytz
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

import accounts.serializers as serializers
from accounts.filters import UserObjectPermissionsFilter
from accounts.models.eula import UserAgreement, EULA
from accounts.permissions import UserObjectPermissions

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

    def get_queryset(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'me':
            self.kwargs[lookup_url_kwarg] = self.request.user.id

        user = self.request.user
        queryset = user.act_as_profiles.all()
        return queryset


class UsersCsvView(generics.RetrieveAPIView):
    permission_classes = (UserObjectPermissions,)

    def get_queryset(self):
        # Filter users based on tech if filter parameter is persent.
        if self.request.GET.get('additional.tech'):
            return get_user_model().objects.filter(
                additional__tech__icontains=self.request.GET.get(
                    'additional.tech'))
        else:
            return get_user_model().objects.all()

    def get(self, request, *args, **kwargs):
        fieldnames = ['Given Name', 'Family Name', 'Group Membership',
                      'E-mail 1 - Type', 'E-mail 1 - Value']
        users = self.get_queryset()
        csv_data = [
            {'Given Name': user.first_name,
             'Family Name': user.last_name,
             'Group Membership': self.request.GET.get('additional.tech'),
             'E-mail 1 - Type': 'other',
             'E-mail 1 - Value': user.email}
            for user in users]

        # Generate CSV attachment and send it with response.
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.datetime.utcnow())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment;' \
                                          'filename=DAS Users({}) {}.csv'.\
            format(self.request.GET.get('additional.tech', ''),
                   timestamp.strftime('%Y-%m-%d %H:%M:%S'))
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        if csv_data:
            writer.writerows(csv_data)
        return response


class AcceptEulaAPIView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.AcceptEulaSerializer
    queryset = UserAgreement.objects.all()


class GetActiveEulaAPIView(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = serializers.EulaSerializer
    queryset = EULA.objects.all()

    def get_object(self):
        return EULA.objects.get(active=True)
