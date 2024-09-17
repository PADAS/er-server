import json
from rest_framework import generics

from buoy import serializers
from buoy.views.schemas import GearsViewSchema
from django.db.models import OuterRef, Subquery
from buoy.views.helpers import check_to_include_inactive_buoys, filter_by_bbox
from django.shortcuts import get_object_or_404
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource, SubjectSource, Observation
from observations.permissions import StandardObjectPermissions
from observations.utils import (
    VIEW_SUBJECT_PERMS,
    dateparse,
    get_minimum_allowed_age,
)
from observations.views.helpers import check_valid_date_string

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
        # allowed = Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True)

        # First get subject-sources. TODO: Look into using allowed users
        queryset = SubjectSource.objects.all()

        # need a stable sort for pagination. this needs to match the distinct
        # parameter set in by_user_subjects
        queryset = check_to_include_inactive_buoys(self.request, queryset)
        queryset = queryset.order_by("id")

        updated_since = self.request.query_params.get("updated_since")
        is_updated_since_valid, updated_since = check_valid_date_string(updated_since, "updated_since")
        if updated_since and is_updated_since_valid:
            queryset = queryset.by_updated_since(updated_since)
        elif updated_since and not is_updated_since_valid:
            raise ValueError("updated_since must be a valid date")

        lat = self.request.query_params.get("lat")
        lon = self.request.query_params.get("lon")
        if lat and lon:
            lat = float(lat)
            lon = float(lon)
            queryset = filter_by_bbox(queryset=queryset, latitude=lat, longitude=lon)
        else:
            raise ValueError("request must include lat and lon")
        
        # Filter queryset by removing subjects where the additional field is the same     
        latest_observations = Observation.objects.filter(source_id=OuterRef("source_id")).order_by("-recorded_at")# [:1]
        queryset.update(additional=Subquery(latest_observations.values("additional")[:1]))

        # TODO: look into select related for perfomance 
        # Keep an eye on performance of the query and potentially add new indexes to improve performance 
        queryset = queryset.order_by('additional').distinct('additional')

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
