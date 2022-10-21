import csv
import datetime
import logging

import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

import accounts.serializers as serializers
from accounts.filters import UserObjectPermissionsFilter
from accounts.models import User
from accounts.models.eula import UserAgreement, EULA
from accounts.permissions import UserObjectPermissions, EulaPermission
from accounts.utils import allowed_permissions

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

    def get_serializer_context(self):
        context = super().get_serializer_context()

        # Add permissions block. Initially this covers just Patrol-related resources.
        context['permissions'] = allowed_permissions(self.request.user) or {}
        return context


class UserProfilesView(generics.ListAPIView):
    lookup_field = 'id'
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer
    permission_classes = (UserObjectPermissions,)

    def get_queryset(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs.get(lookup_url_kwarg) == 'me':
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
    permission_classes = (IsAuthenticated, EulaPermission)
    serializer_class = serializers.AcceptEulaSerializer
    queryset = UserAgreement.objects.all()

    def create(self, request, *args, **kwargs):
        user_id = request.data.get("user")
        eula_id = request.data.get("eula")
        accepted = request.data.get("accept", True)

        # accept=False, so revoke eula
        if not accepted:
            try:
                user = User.objects.get(id=user_id)
                user.accepted_eula = False
                user.save()

                UserAgreement.objects.filter(user=user, eula_id=eula_id).delete()
                return Response(request.data, status=status.HTTP_200_OK)

            except User.DoesNotExist:
                return Response({"error": f'User ID {user_id} does not exist.'}, status=status.HTTP_400_BAD_REQUEST)

        # Otherwise normal case where user has accepted a Eula.
        try:
            ua = UserAgreement.objects.get(user=user_id, eula_id=eula_id)
            ua.save() # Let .save() handle dependent updates (ex. on User).

            return Response(request.data, status=status.HTTP_200_OK)

        except UserAgreement.DoesNotExist:
            return super(AcceptEulaAPIView, self).create(request, *args, **kwargs)


class GetActiveEulaAPIView(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = serializers.EulaSerializer
    queryset = EULA.objects.all()

    def dispatch(self, request, *args, **kwargs):
        if not settings.ACCEPT_EULA:
            self.headers = self.default_response_headers
            response = Response(data={
                "message": "Site doesn't require users to accept a EULA"},
                status=status.HTTP_200_OK)
            return self.finalize_response(request, response, *args, **kwargs)

        return super(GetActiveEulaAPIView, self).dispatch(request, *args, **kwargs)

    def get_object(self):
        return EULA.objects.get(active=True)
