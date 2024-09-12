from rest_framework import generics

from buoy import serializers
from buoy.views.schemas import GearsViewSchema
from django.db.models import F
from django.shortcuts import get_object_or_404
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource
from observations.permissions import StandardObjectPermissions
from observations.utils import (
    VIEW_SUBJECT_PERMS,
    dateparse,
    get_minimum_allowed_age,
)

from utils.drf import (
    ForbiddenAPIException,
    StandardResultsSetPagination,
)


class GearsView(generics.ListAPIView):
    """
    get:
    Returns a list of Gear in the system.

    """

    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearsSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
        query_params = self.request.query_params
        allowed = Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True)

        # First get subject-sources user has access to.
        queryset = SubjectSource.objects.filter(subject_id__in=allowed)

        # Filter queryset by removing subjects where the additional field is the same        
        queryset = queryset.annotate(
            subjectsource_additional=F("source__subjectsource__additional"),
        )
        queryset = queryset.distinct("source__subjectsource__additional")

        return queryset


class GearView(generics.RetrieveUpdateDestroyAPIView, TwoWaySubjectSourceMixin):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearSerializer
    lookup_field = "id"

    def check_permissions(self, request):
        subject_id = self.kwargs.get("id")
        self.queryset_linked_user = Subject.objects.filter(linked_user=request.user, id=subject_id)
        if not self.queryset_linked_user.exists():
            for permission in self.get_permissions():
                if not permission.has_permission(request, self):
                    self.permission_denied(request)

    def get_queryset(self):
        subject_id = self.kwargs.get("id")
        subject = generics.get_object_or_404(Subject.objects.all(), pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise ForbiddenAPIException
        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = Subject.objects.filter(id=subject_id)
        mou_date = self.request.user.additional.get("expiry", None)
        mou_date = dateparse(mou_date) if mou_date else None
        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_date)
        self._get_two_way_sources(queryset)
        return queryset

    def get_object(self):
        if self.queryset_linked_user.exists():
            subject_id = self.kwargs.get("id")
            return get_object_or_404(self.queryset_linked_user, pk=subject_id)
        return super().get_object()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources

        return context
