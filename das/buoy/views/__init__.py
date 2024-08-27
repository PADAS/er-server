from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics

from buoy import serializers
from observations import models
from observations.mixins import TwoWaySubjectSourceMixin
from observations.permissions import StandardObjectPermissions
from observations.utils import VIEW_SUBJECT_PERMS, dateparse, get_minimum_allowed_age
from utils.drf import ForbiddenAPIException


class GearView(generics.RetrieveUpdateDestroyAPIView, TwoWaySubjectSourceMixin):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearSerializer
    lookup_field = "id"

    def check_permissions(self, request):
        gear_subject_id = self.kwargs.get("id")
        self.queryset_linked_user = models.Subject.objects.filter(linked_user=request.user, id=gear_subject_id)
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        gear_subject_id = self.kwargs.get("id")
        gear_subject = generics.get_object_or_404(models.Subject.objects.all(), pk=gear_subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, gear_subject):
            raise ForbiddenAPIException
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = models.Subject.objects.filter(id=gear_subject_id)
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
        self._get_two_way_sources(queryset)
        return queryset

    def get_object(self):
        if self.queryset_linked_user.exists():
            gear_subject_id = self.kwargs.get("id")
            return get_object_or_404(self.queryset_linked_user, pk=gear_subject_id)
        return super().get_object()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources

        return context


def GearsView(request):
    return HttpResponse("GearsView")
