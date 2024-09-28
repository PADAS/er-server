import json
from rest_framework import generics

from buoy import serializers
from buoy.views.helpers import (
    check_valid_state_string,
    check_valid_date_string,
)
from buoy.views.schemas import GearsViewSchema
from django.db.models import OuterRef, Subquery
from buoy.views.helpers import check_to_include_inactive_buoys, filter_by_bbox
from django.shortcuts import get_object_or_404
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Subject, SubjectSource, SubjectSource, LatestObservationSource
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
from utils.gis import check_valid_lat_lon


class GearsView(generics.ListAPIView):
    __doc__ = """
    Returns all gears.
    
    Required query-parameters:
    lat, lon: float
    
    Optional query-parameters:
    state, where state is either "deployed" or "hauled".
        example: state=deployed
    updated_since, where updated_since is a date-string to limit on updated_at

    page, page number

    page_size, (default is {page_size}, max is {max_page_size})
    """.format(
        page_size=StandardResultsSetPagination.page_size, max_page_size=StandardResultsSetPagination.max_page_size
    )

    permission_classes = (StandardObjectPermissions,)
    serializer_class = serializers.GearsSerializer
    pagination_class = StandardResultsSetPagination
    schema = GearsViewSchema()

    def get_queryset(self):
        query_params = self.request.query_params
        # TODO: Look into using allowed users - need to add subjects to SG in unit tests
        # allowed = Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True)

        # First get subject-sources.
        queryset = SubjectSource.objects.all().select_related("source").select_related("subject")

        # need a stable sort for pagination. 
        queryset = check_to_include_inactive_buoys(self.request, queryset)
        queryset = queryset.order_by("id")

        updated_since = query_params.get("updated_since")
        is_updated_since_valid, updated_since = check_valid_date_string(updated_since, "updated_since")
        if updated_since and is_updated_since_valid:
            queryset = queryset.by_updated_since(updated_since)
        elif updated_since and not is_updated_since_valid:
            raise ValueError("updated_since must be a valid date")

        # Filter queryset by deployed/hauled status
        is_active_valid, is_active = check_valid_state_string(query_params.get("state"))
        if is_active_valid and is_active:
            queryset = queryset.filter(subject__is_active=True)
        elif is_active_valid and not is_active:
            queryset = queryset.filter(subject__is_active=False)

        lat = query_params.get("lat")
        lon = query_params.get("lon")
        if lat and lon:
            lat = float(lat)
            lon = float(lon)
            is_lat_lon_valid = check_valid_lat_lon(latitude=lat, longitude=lon)
            if not is_lat_lon_valid:
                raise ValueError("lat and lon are invalid values")
            queryset = filter_by_bbox(queryset=queryset, latitude=lat, longitude=lon)
        else:
            return queryset.none()
        
        # Filter queryset by removing subjects where the additional field is the same 
        latest_observation = LatestObservationSource.objects.filter(source_id=OuterRef("source_id")) 
        queryset.update(additional=Subquery(latest_observation.values("observation__additional")[:1]))

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
