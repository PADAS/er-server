import csv
import datetime
import logging

import pytz
from django_filters import rest_framework as filters
from rest_framework_condition import etag

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.filters import UserFilterSet, UserObjectPermissionsFilter
from accounts.models import User
from accounts.models.eula import EULA, UserAgreement
from accounts.permissions import EulaPermission, UserObjectPermissions
from accounts.serializers import AcceptEulaSerializer, EulaSerializer, UserSerializer
from accounts.utils import allowed_permissions
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.tenant import get_tenant_settings

from .utils import get_user_etag

logger = logging.getLogger(__name__)


class UsersView(generics.ListAPIView, DynamicSchemaDataMixin):
    serializer_class = UserSerializer
    permission_classes = (UserObjectPermissions,)
    filter_backends = (UserObjectPermissionsFilter, filters.DjangoFilterBackend)
    filterset_class = UserFilterSet

    def get_queryset(self):
        return get_user_model().objects.all()


class UserView(generics.RetrieveAPIView):
    lookup_field = "id"
    serializer_class = UserSerializer
    permission_classes = (UserObjectPermissions,)
    filter_backends = (UserObjectPermissionsFilter, filters.DjangoFilterBackend)
    filterset_class = UserFilterSet

    def get_queryset(self):
        return get_user_model().objects.all()

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == "me":
            self.kwargs[lookup_url_kwarg] = self.request.user.id
        return super(UserView, self).get_object()

    @etag(get_user_etag)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Add permissions block. Initially this covers just Patrol-related resources.
        context["permissions"] = allowed_permissions(self.request.user) or {}
        return context


class UserProfilesView(generics.ListAPIView):
    lookup_field = "id"
    serializer_class = UserSerializer
    permission_classes = (UserObjectPermissions,)

    @etag(get_user_etag)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs.get(lookup_url_kwarg) == "me":
            self.kwargs[lookup_url_kwarg] = self.request.user.id

        user = self.request.user
        queryset = user.act_as_profiles.all()
        return queryset


class UsersCsvView(APIView):
    permission_classes = (UserObjectPermissions,)

    def get_queryset(self):
        # Filter users based on tech if filter parameter is persent.
        if self.request.GET.get("additional.tech"):
            return get_user_model().objects.filter(additional__tech__icontains=self.request.GET.get("additional.tech"))
        else:
            return get_user_model().objects.all()

    def get(self, request, *args, **kwargs):
        fieldnames = ["Given Name", "Family Name", "Group Membership", "E-mail 1 - Type", "E-mail 1 - Value"]
        users = self.get_queryset()
        csv_data = [
            {
                "Given Name": user.first_name,
                "Family Name": user.last_name,
                "Group Membership": self.request.GET.get("additional.tech"),
                "E-mail 1 - Type": "other",
                "E-mail 1 - Value": user.email,
            }
            for user in users
        ]

        # Generate CSV attachment and send it with response.
        current_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = current_tz.localize(datetime.datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
        additional_tech = self.request.GET.get("additional.tech", "")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment;" f"filename=DAS Users({additional_tech}) {timestamp}.csv"
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        if csv_data:
            writer.writerows(csv_data)
        return response


class AcceptEulaAPIView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated, EulaPermission)
    serializer_class = AcceptEulaSerializer

    def get_queryset(self):
        return UserAgreement.objects.all()

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
                return Response({"error": f"User ID {user_id} does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        # Otherwise normal case where user has accepted a Eula.
        try:
            ua = UserAgreement.objects.get(user=user_id, eula_id=eula_id)
            ua.save()  # Let .save() handle dependent updates (ex. on User).

            return Response(request.data, status=status.HTTP_200_OK)

        except UserAgreement.DoesNotExist:
            return super(AcceptEulaAPIView, self).create(request, *args, **kwargs)


class GetActiveEulaAPIView(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = EulaSerializer

    def get_queryset(self):
        return EULA.objects.all()

    def dispatch(self, request, *args, **kwargs):
        if not get_tenant_settings().env_settings.accept_eula:
            self.headers = self.default_response_headers
            response = Response(
                data={"message": "Site doesn't require users to accept a EULA"}, status=status.HTTP_200_OK
            )
            return self.finalize_response(request, response, *args, **kwargs)

        return super(GetActiveEulaAPIView, self).dispatch(request, *args, **kwargs)

    def get_object(self):
        return EULA.objects.get(active=True)
