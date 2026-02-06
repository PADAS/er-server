import datetime
import json
import logging
import re
import urllib

import dateutil.parser
import pytz
from kombu import exceptions

import django
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Q, QuerySet, Window
from django.db.models.functions import RowNumber
from django.db.models.query import RawQuerySet
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.exceptions import ParseError, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import UserCanExportDataPermission
from core.view_utils import AsyncDeleteObjectMixin
from das_server import celery
from das_server.views import CustomSchema
from observations import kmlutils
from observations.filters import SubjectObjectPermissionsFilter, create_gp_filter_class
from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import (
    GPX_FILES_FOLDER,
    RECEIVED,
    Announcement,
    Message,
    Observation,
    Region,
    Source,
    SourceGroup,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectStatus,
    SubjectSubType,
)
from observations.serializers import (
    AnnouncementSerializer,
    GPXTrackFileUploadSerializer,
    MessageSerializer,
    ObservationSerializer,
    ReadAnnouncementSerializer,
    RegionSerializer,
    SourceProviderSerializer,
    SourceSerializer,
    SubjectSerializer,
    SubjectSourceSerializer,
    SubjectStatusSerializer,
    SubjectTrackSerializer,
    TrackLimitSerializer,
    TrackSerializer,
    create_sg_serializer,
)
from observations.tasks import handle_outbox_message, process_gpxdata_api
from observations.utils import (
    VIEW_OBSERVATION_PERMS,
    VIEW_SUBJECT_PERMS,
    calculate_subject_view_window,
    check_to_include_inactive_subjects,
    dateparse,
    get_minimum_allowed_age,
    parse_comma,
)
from observations.views.observations import FlattenObservationsView, ObservationsView
from observations.views.schemas import InactiveSubjectsViewSchema
from observations.views.subjects import (
    SubjectGroupSubjectsView,
    SubjectGroupsView,
    SubjectGroupView,
    SubjectsGeoJsonView,
    SubjectsView,
    SubjectView,
)
from observations.views.utils import (
    get_subjects_with_observations_in_daterange,
    get_track_days,
)
from utils import add_base_url
from utils.drf import (
    ForbiddenAPIException,
    StandardObjectPermissions,
    StandardResultsSetPagination,
)
from utils.features import features
from utils.json import parse_bool, zeroout_microseconds
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)


current_tz_name = timezone.get_current_timezone_name()
current_tz = pytz.timezone(current_tz_name)
current_date = datetime.datetime.utcnow().astimezone(current_tz)
tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
tz_offset = (
    "GMT"
    + ("+" if tz_difference >= 0 else "")
    + str(int(tz_difference))
    + ":"
    + str(int((tz_difference - int(tz_difference)) * 60))
)


class RegionsView(generics.ListAPIView):
    lookup_field = "slug"
    serializer_class = RegionSerializer

    def get_queryset(self):
        return Region.objects.all()


class RegionView(generics.RetrieveAPIView):
    lookup_field = "slug"
    queryset = Region.objects.all()
    serializer_class = RegionSerializer

    def get_queryset(self):
        return Region.objects.all()


class SourceGroupsView(generics.ListAPIView):
    """
    Returns all sourcegroups in the system.
    """

    serializer_class = create_sg_serializer("sourcegs", SourceGroup, SourceSerializer)
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (create_gp_filter_class("sourcegf", ("observations.view_sourcegroup",), SourceGroup),)

    def get_queryset(self):
        queryset = SourceGroup.objects.filter(_parents=None)
        # Sorting SourceGroups based on name (use '-name' for descending order)
        queryset = queryset.order_by("name")
        return queryset


class SourceGroupView(generics.ListAPIView):
    """
    Return all sources of given source Group (sourcegroup/sources/<name/id>/)
    """

    serializer_class = SourceSerializer
    lookup_field = "slug"  # slug can have value of source group's name or id

    def get_queryset(self):
        slug = self.kwargs["slug"]
        source_group = SourceGroup.objects.filter(name=slug).first()
        if not source_group:
            source_group = SourceGroup.objects.filter(id=slug).first()
        if source_group:
            return source_group.get_all_sources()
        return None


class RegionSubjectsView(generics.ListAPIView, TwoWaySubjectSourceMixin):
    lookup_field = "slug"
    serializer_class = SubjectSerializer
    permission_classes = (StandardObjectPermissions,)
    filter_backends = (SubjectObjectPermissionsFilter,)

    schema = InactiveSubjectsViewSchema()

    def get_queryset(self):
        region = generics.get_object_or_404(Region.objects.all(), slug=self.kwargs.get("slug"))
        queryset = Subject.objects.all()
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        subjects = queryset.by_region(region).annotate_with_subjectstatus()

        return subjects

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources

        return context


class SubjectSubjectSourcesView(generics.ListAPIView):
    """View for a Subject's SubjectSource records"""

    serializer_class = SubjectSourceSerializer

    def get_queryset(self, *args, **kwargs):
        subject = get_object_or_404(Subject, pk=self.kwargs["id"])
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied
        return SubjectSource.objects.get_subject_sources(subject)


class SubjectSourcesView(generics.ListCreateAPIView):
    serializer_class = SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            Subject.objects.all(), pk=self.kwargs["id"]
        )  # <-- Maybe annotate with subject_status
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied
        subject_sources = SubjectSource.objects.get_subject_sources(subject)
        sources = Source.objects.filter(pk__in=subject_sources.values("source"))
        return sources

    def create(self, request, *args, **kwargs):
        request.data["subject"] = self.kwargs["id"]
        serializer = SubjectSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SourceSubjectsView(generics.ListCreateAPIView, TwoWaySubjectSourceMixin):
    serializer_class = SubjectSerializer

    def get_queryset(self):
        source = generics.get_object_or_404(Source.objects.all(), pk=self.kwargs["id"])
        # if not self.request.user.has_any_perms(models.Source.VIEW_SUBJECT_PERMS, source):
        #     raise PermissionDenied
        queryset = Subject.objects.all()
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        self._get_two_way_sources(queryset)
        return queryset.filter(subjectsource__source=source).annotate_with_subjectstatus()

    def create(self, request, *args, **kwargs):
        request.data["subject"] = self.kwargs["id"]
        serializer = SubjectSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["two_way_subject_sources"] = self.two_way_subject_sources
        return context


class SubjectSourceView(generics.RetrieveAPIView):
    serializer_class = SourceSerializer

    def get_queryset(self):
        subject = generics.get_object_or_404(
            Subject.objects.all(), pk=self.kwargs["id"]
        )  # .annotate_with_subjectstatus()
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        return Source.objects.all()

    def get_object(self):
        queryset = self.get_queryset()
        filters = {"id": self.kwargs["source_id"]}

        obj = generics.get_object_or_404(queryset, **filters)
        self.check_object_permissions(self.request, obj)
        return obj


class SubjectSourceTrackView(generics.RetrieveAPIView):
    lookup_field = "id"
    serializer_class = TrackSerializer
    permission_classes = (StandardObjectPermissions,)
    schema = None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        subject = self.get_object()
        source_id = self.kwargs["source_id"]

        since = self.request.query_params.get("since", None)
        if isinstance(since, str):
            since = dateparse(since)

        until = self.request.query_params.get("until", None)
        if until:
            until = dateparse(until)

        sds = SubjectSource.objects.get_subject_source(subject, source_id)
        if not sds:
            raise Http404

        if since is None:
            since = datetime.datetime.now(tz=pytz.UTC) - get_track_days()

        coordinates = []
        times = []
        for ob in Observation.objects.get_subject_source_observation_values(sds, since, until):
            coordinates.append(ob["location"].coords)
            times.append(zeroout_microseconds(ob["recorded_at"]))

        context["times"] = times
        context["coordinates"] = coordinates
        return context

    def get_queryset(self):
        return Subject.objects.all()


class SubjectStatusView(generics.RetrieveAPIView):
    lookup_url_kwarg = "subject_id"
    lookup_field = "subject_id"
    serializer_class = SubjectStatusSerializer

    def get_queryset(self):
        ss = SubjectStatus.objects.select_related("subject").filter(delay_hours=0)
        return ss

    def check_object_permissions(self, request, obj):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, obj.subject):
            raise PermissionDenied


class SubjectTracksView(generics.RetrieveAPIView):
    """
    Optional qparam of:
    limit
    since starting date range for the requested track, default follow the tracks logic of returning x number of days. ISO date/time
    until stop date range for the requested track, default is now. ISO date/time
    """

    lookup_url_kwarg = "subject_id"
    serializer_class = SubjectTrackSerializer

    def get_queryset(self):
        self.subject_linked_sources = []
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        queryset = Subject.objects.all().select_related("subject_subtype__subject_type")
        queryset = queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24)

        return queryset

    def check_object_permissions(self, request, obj):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, obj):
            source_groups = SourceGroup.objects.filter(permission_sets__in=request.user.get_all_permission_sets())
            all_allowed_sources = []
            for source_group in source_groups:
                all_allowed_sources.extend(source_group.get_all_sources())

            # Check if Subject's current source
            subject_sources = SubjectSource.objects.get_subject_sources(obj)
            sources = Source.objects.filter(pk__in=subject_sources.values("source"))

            pass_flag = False
            for source in sources:
                if source in all_allowed_sources:
                    self.subject_linked_sources.append(source)
                    pass_flag = True

            if not pass_flag:
                raise PermissionDenied

    def get_object(self):
        try:
            return self._cached_object
        except AttributeError:
            pass
        self._cached_object = super().get_object()

        return self._cached_object

    def get_serializer_context(self):
        context = super().get_serializer_context()

        tracks_limits = TrackLimitSerializer(data=self.request.query_params)
        tracks_limits.is_valid(raise_exception=True)
        context["tracks_limit"] = tracks_limits.validated_data["limit"]

        since = self.request.query_params.get("since", None)
        until = self.request.query_params.get("until", None)

        linked_sources = getattr(self, "subject_linked_sources", None)

        context["tracks_since"] = None
        context["tracks_until"] = None

        if since is not None:
            context["tracks_since"] = dateparse(since)

        if until is not None:
            context["tracks_until"] = dateparse(until)

        context["subject_linked_sources"] = linked_sources

        return context


class ObservationView(generics.RetrieveUpdateDestroyAPIView):
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    lookup_field = "id"
    serializer_class = ObservationSerializer

    def get_queryset(self):
        if not self.request.user.has_any_perms(VIEW_OBSERVATION_PERMS):
            raise ForbiddenAPIException

        queryset = Observation.objects.all()

        mou_date = self.request.user.additional.get("expiry", None)
        mou_expiry_date = dateparse(mou_date) if mou_date else None

        if mou_expiry_date:
            queryset = queryset.filter(recorded_at__lte=mou_expiry_date)
        return queryset


class SourceView(AsyncDeleteObjectMixin, generics.RetrieveUpdateDestroyAPIView, generics.CreateAPIView):
    lookup_fields = ("id", "manufacturer_id")
    serializer_class = SourceSerializer

    def get_object(self):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        filter = {}

        for p in self.lookup_fields:
            pval = self.kwargs.get(p, None)
            if pval is not None:
                filter[p] = pval

        return generics.get_object_or_404(queryset, **filter)

    def get_queryset(self):
        return Source.objects.all()


class SourcesView(
    generics.ListCreateAPIView,
):
    serializer_class = SourceSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination

    lookup_fields = {
        "manufacturer_id": "manufacturer_id__in",
        "provider_key": "provider__provider_key__in",
        "provider": "provider__provider_key__in",
        "id": "id__in",
    }

    def get_queryset(self):
        queryset = Source.objects.all()

        filter = {}
        for fn, fld in self.lookup_fields.items():
            if fn in self.request.query_params:
                filter[fld] = parse_comma(self.request.query_params.get(fn))
        if filter:
            queryset = queryset.filter(**filter)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class SourceProvidersView(generics.ListCreateAPIView):
    serializer_class = SourceProviderSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination

    lookup_field = "provider_key"

    def get_queryset(self):
        queryset = SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class SourceProvidersViewPartial(generics.UpdateAPIView):
    serializer_class = SourceProviderSerializer
    permission_classes = (StandardObjectPermissions,)
    lookup_field = "id"

    def get_queryset(self):
        queryset = SourceProvider.objects.all()
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context


class KmlRootView(APIView):
    permission_classes = (UserCanExportDataPermission,)
    renderer_classes = (StaticHTMLRenderer,)

    def build_link_for_user(self, start_date=None, end_date=None):
        token = kmlutils.get_kml_access_token(
            self.request.user,
        )
        include_active = self.request.GET.get("include_inactive")
        include_active = parse_bool(include_active)
        params = {
            k: v
            for k, v in zip(["auth", "start", "end", "include_inactive"], [token, start_date, end_date, include_active])
            if v
        }
        params = urllib.parse.urlencode(params)
        url = reverse("subjects-kml-view")
        return add_base_url(self.request, f"{url}?{params}")

    def get(self, request, *args, **kwargs):
        start_date = self.request.GET.get("start")
        end_date = self.request.GET.get("end")
        start = None
        end = None

        if start_date:
            try:
                start_date = dateutil.parser.parse(start_date)
                start = start_date.isoformat()
            except Exception as e:
                return Response(data={"start": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_date = dateutil.parser.parse(end_date)
                end = end_date.isoformat()
            except Exception as e:
                return Response(data={"end": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Have a configuration for naming the KML feed.
        filename = "DAS-KML_{}_{}".format(
            self.request.user.username, datetime.datetime.now(tz=pytz.utc).strftime("%Y%M%d%H%M")
        )

        context = {
            "network_link": {
                "name": get_tenant_settings().env_settings.kml_feed_title,
                "visibility": 0,
                "open": 1,
                "href": self.build_link_for_user(start, end),
            }
        }

        result = render_to_string("kml/user_root.xml", context)

        return kmlutils.render_to_kmz(result, filename)


class KmlSubjectsView(APIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer,)

    def get_queryset(self):
        include_inactive = self.request.GET.get("include_inactive")

        start_date = self.request.GET.get("start")
        end_date = self.request.GET.get("end")

        # verify date in YYYY-mm-dd
        try:
            dateutil.parser.parse(start_date)
        except Exception:
            start_date = None

        try:
            dateutil.parser.parse(start_date)
        except Exception:
            end_date = None

        if start_date or end_date:
            queryset = get_subjects_with_observations_in_daterange(start_date, end_date)
        else:
            # return all subjects with or without tracks if no date
            # filter is passed
            queryset = Subject.objects.all()
        queryset = queryset.by_user_subjects(self.request.user)
        queryset = queryset.by_include_inactive(include_inactive)

        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        return queryset.annotate_with_subjectstatus(delay_hours=min_age_days * 24)

    def build_link_for_subject(self, subject):
        token = kmlutils.get_kml_access_token(self.request.user)
        start_date = self.request.GET.get("start")
        end_date = self.request.GET.get("end")
        params = {k: v for k, v in zip(["auth", "start", "end"], [token, start_date, end_date]) if v}
        params = urllib.parse.urlencode(params)
        url = reverse("subject-kml-view", args=[subject["id"]])
        return add_base_url(self.request, f"{url}?{params}")

    def subject_context(self, subject):
        return {"name": subject.name, "visibility": 0, "href": self.build_link_for_subject(subject)}

    @staticmethod
    def get_display_subtype(subtype):
        """
        Get the human name or subtype.
        :param subtype:
        :return:
        """
        try:
            return SubjectSubType.objects.get(value=subtype).display
        except Exception as e:
            logger.exception(e)
            return "Unassigned"

    def get(self, request, *args, **kwargs):
        subjects = list(self.get_queryset().values("additional", "name", "id", "subject_subtype"))

        DEFAULT_REGION_NAME = "Unknown Region"

        subject_list = [
            {
                "name": subject["name"],
                "species": self.get_display_subtype(subject.get("subject_subtype")),
                "region": (
                    subject.get("additional").get("region")
                    if isinstance(subject.get("additional").get("region"), str)
                    else DEFAULT_REGION_NAME
                ),
                "visibility": 0,
                "href": self.build_link_for_subject(subject),
            }
            for subject in subjects
        ]
        #
        context = {"title": "DAS Tracking Data", "visibility": 1, "subject_list": subject_list}

        filename = "DAS-KML-Subjects_{}_{}".format(
            self.request.user.username, datetime.datetime.now(tz=pytz.utc).strftime("%Y%M%d%H%M")
        )

        result = render_to_string("kml/subject_list.xml", context)
        return kmlutils.render_to_kmz(result, filename)


def rgb_to_hex(red, green, blue):
    """Return color as #rrggbb for the given color values."""
    return "ff%02x%02x%02x" % (int(red), int(green), int(blue))


class KmlSubjectView(generics.RetrieveAPIView):
    permission_classes = (StandardObjectPermissions,)
    renderer_classes = (StaticHTMLRenderer,)
    lookup_field = "id"

    def get_queryset(self):
        subject = generics.get_object_or_404(Subject.objects.all(), pk=self.kwargs.get("id"))
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        min_age_days = get_minimum_allowed_age(self.request.user) or 0
        queryset = Subject.objects.all().annotate_with_subjectstatus(delay_hours=min_age_days * 24)
        return queryset

    def get_subject_color(self, subject):
        """
        Be careful reusing this function. Take note of the unusual order of hues in the result.
        :param subject:
        :return:
        """
        try:
            red, green, blue = subject.additional["rgb"].split(",")
            kml_color = "ff%02x%02x%02x" % (int(blue), int(green), int(red))
        except:
            kml_color = "ff000000"  # Default is black.

        return kml_color

    def get_allowed_subject_observations(self, subject, filter_parameters=None):
        start_timestamp = filter_parameters.get("start")
        end_timestamp = filter_parameters.get("end")
        filter_flag = filter_parameters.get("filter", 0)

        maximum_history_days = 60
        if start_timestamp:
            delta = datetime.datetime.now(pytz.utc) - start_timestamp
            if delta.days > maximum_history_days:
                maximum_history_days = delta.days
        (lower, upper) = calculate_subject_view_window(self.request.user, maximum_history_days)

        if lower >= upper:
            raise PermissionDenied

        if start_timestamp and upper >= start_timestamp >= lower:
            lower = start_timestamp
        if end_timestamp and upper >= end_timestamp >= lower:
            upper = end_timestamp
        if start_timestamp and end_timestamp and end_timestamp < start_timestamp:
            raise ValueError("Start date can not be greater than end date.")

        return Observation.objects.get_subject_observations_values(
            subject, since=lower, until=upper, filter_flag=filter_flag
        )

    def parse_filter_parameters(self):
        """
        Parse GET request filter parameters.
        :return: Dict of filter parameters in the appropriate format.
        """
        filter_parameters = {}
        try:
            if self.request.GET.get("start"):
                filter_parameters.update({"start": dateutil.parser.parse(self.request.GET.get("start"))})
        except (ValueError, TypeError):
            raise ValueError("Invalid start-date format - {}".format(self.request.GET.get("start")))
        try:
            if self.request.GET.get("end"):
                filter_parameters.update({"end": dateutil.parser.parse(self.request.GET.get("end"))})
        except (ValueError, TypeError):
            raise ValueError("Invalid end-date format - {}".format(self.request.GET.get("end")))
        try:
            if self.request.GET.get("filter"):
                filter_parameters.update({"filter": int(self.request.GET.get("filter", 0))})
        except (ValueError, TypeError):
            raise ValueError("Invalid filter flag format - {}".format(self.request.GET.get("filter")))
        return filter_parameters

    def get(self, request, *args, **kwargs):
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        subject = generics.get_object_or_404(
            Subject.objects.all().annotate_with_subjectstatus(delay_hours=min_age_days * 24),
            pk=self.kwargs["id"],
        )
        filter_parameters = self.parse_filter_parameters()
        self.check_object_permissions(self.request, subject)

        observations = list(self.get_allowed_subject_observations(subject, filter_parameters))

        filename = "DAS-KML_{}-{}".format(
            re.sub("[^a-zA-Z0-9]", "_", subject.name), datetime.datetime.now(tz=pytz.utc).strftime("%Y%M%d%H%M")
        )

        kml_overlay_image = get_tenant_settings().env_settings.kml_overlay_image

        color = self.get_subject_color(subject)
        context = {
            "name": subject.name,
            "observations": observations,
            "points_color": color,
            "track_color": color,
            "last_position_color": color,
            "subject_icon": add_base_url(request, subject.kml_image_url),
            "kml_overlay_image": add_base_url(request, kml_overlay_image) if kml_overlay_image else None,
            "timezone_name": current_tz_name,
            "timezone": current_tz,
        }
        result = render_to_string("kml/subject_track.xml", context)
        return kmlutils.render_to_kmz(result, filename)


class TrackingDataViewSchema(InactiveSubjectsViewSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {
                    "name": "current_status",
                    "in": "query",
                    "description": "Get current status or historical observations",
                    "schema": {"type": "bool"},
                },
                {
                    "name": "subject_id",
                    "in": "query",
                    "description": "Get data for specific subject ID",
                    # 'schema': {'type': 'integer'}
                },
                {
                    "name": "subject_chronofile",
                    "in": "query",
                    "description": "Get data for specific chronofiles",
                    "schema": {"type": "integer"},
                },
                {
                    "name": "source_provider",
                    "in": "query",
                    "description": "Get data for specific source provider. Use the source provider key, ie 'default'",
                    "schema": {"type": "string"},
                },
                {
                    "name": "filter",
                    "in": "query",
                    "description": "Add Exclusion flags as a bitmap. oneof [null, 0, 1, 2, 3]",
                    # 'schema': {'type': 'integer'}
                },
                {
                    "name": "format",
                    "in": "query",
                    "description": "Return report as CSV or JSON",
                    "schema": {"type": "string"},
                },
                {
                    "name": "before_date",
                    "in": "query",
                    "description": "Return report before given date",
                    # 'schema': {'type': 'string'}
                },
                {
                    "name": "after_date",
                    "in": "query",
                    "description": "Return report after given date",
                    # 'schema': {'type': 'string'}
                },
                {
                    "name": "record_serial_base",
                    "in": "query",
                    "description": "Return report in order of generated serial number",
                    # 'schema': {'type': 'bool'}
                },
                {
                    "name": "max_records",
                    "in": "query",
                    "description": "Maximum number of records to return",
                    "schema": {"type": "integer"},
                },
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)
        return operation


class TrackingDataCsvView(APIView):
    permission_classes = (UserCanExportDataPermission, StandardObjectPermissions)
    schema = TrackingDataViewSchema()

    def get_queryset(self, subject_id=None, chronofile=None, source_provider=None):
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS):
            raise PermissionDenied
        queryset = Subject.objects.all()
        # To include inactive subjects in trackingdata report
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.by_user_subjects(self.request.user)
        if subject_id:
            queryset = queryset.filter(id=subject_id)
        elif source_provider:
            queryset = queryset.filter(subjectsource__source__provider__provider_key=source_provider)
        elif chronofile:
            queryset = queryset.filter(subjectsource__additional__chronofile=int(chronofile))

            queryset = (
                queryset.annotate(subjectsource_additional=F("subjectsource__additional"))
                .annotate(source_model_name=F("subjectsource__source__model_name"))
                .annotate(source_manufacturer_id=F("subjectsource__source__manufacturer_id"))
                .annotate(subjectsource_assigned_range=F("subjectsource__assigned_range"))
                .annotate(source_additional=F("subjectsource__source__additional"))
                .annotate(source_id=F("subjectsource__source__id"))
                .annotate(subjectsource_id=F("subjectsource__id"))
            )
        return queryset

    def _get_fieldnames(self, result_format, request_subject_id):
        """Get CSV field names with timezone-aware labels."""
        fixtime_label = "fixtime ({})".format(tz_offset) if result_format == "csv" else "fixtime"
        dloadtime_label = "dloadtime ({})".format(tz_offset) if result_format == "csv" else "dloadtime"
        fieldnames = [
            "chronofile",
            "recordserial",
            "observation_id",
            "collar_id",
            fixtime_label,
            dloadtime_label,
            "lon",
            "lat",
            "height",
            "temp",
            "voltage",
            "activity",
            "activity_label",
            "subject_name",
        ]
        if request_subject_id:
            fieldnames = [item.replace("chronofile", "subject_id") for item in fieldnames]
        return fieldnames, fixtime_label, dloadtime_label

    def _generate_current_status_rows(
        self,
        max_records,
        request_subject_id,
        request_subject_chronofile,
        request_source_provider,
        result_format,
        fixtime_label,
        dloadtime_label,
        record_serial_base,
    ):
        """Generator for current status data."""
        items = self.get_subject_status_queryset(
            max_records, request_subject_id, request_subject_chronofile, request_source_provider
        )
        cur_record_serial = record_serial_base
        for item in items.iterator(chunk_size=2000):
            cur_record_serial += 1
            yield self.get_csv_observation_data(
                cur_record_serial,
                dloadtime_label,
                fixtime_label,
                result_format,
                item,
                item["subject_id"] if request_subject_id else None,
                None,
            )

    def _generate_observation_rows(
        self,
        filter_flag,
        lower,
        upper,
        max_records,
        request_subject_id,
        request_subject_chronofile,
        request_source_provider,
        result_format,
        fixtime_label,
        dloadtime_label,
        record_serial_base,
    ):
        """
        Generator for observation data rows.
        Streams rows as they're fetched from the database.
        """
        cur_record_serial = record_serial_base

        try:
            subjects = self.get_queryset(request_subject_id, request_subject_chronofile, request_source_provider)
            for subject in subjects.iterator(chunk_size=100):
                # Get observations for this subject and stream them
                observations_qs = self.get_subject_trackdata_queryset(filter_flag, lower, subject, upper, max_records)
                for item in observations_qs.values().iterator(chunk_size=2000):
                    cur_record_serial += 1
                    yield self.get_csv_observation_data(
                        cur_record_serial,
                        dloadtime_label,
                        fixtime_label,
                        result_format,
                        item,
                        subject.id if request_subject_id else None,
                        None,
                    )
        except django.core.exceptions.ValidationError:
            raise ValidationError({"Error": f"{request_subject_id} is not a valid UUID"})

    def get(self, request, *args, **kwargs):
        from utils.csv_streaming import StreamingCSVResponse

        # Set exclusion flag value
        filter_flag = 0
        qparam = self.request.GET.get("filter", 0)
        try:
            filter_flag = int(qparam)
        except (ValueError, TypeError):
            filter_flag = None if qparam == "null" else filter_flag

        try:
            request_date_after = parse_datetime(self.request.GET.get("after_date", None))
        except Exception:
            request_date_after = None

        try:
            request_date_before = parse_datetime(self.request.GET.get("before_date", None))
        except Exception:
            request_date_before = None

        # return in json format or csv, default is csv
        result_format = self.request.GET.get("format", "csv").lower()

        # get data for a specific subject This is for STE downloader
        request_subject_id = self.request.GET.get("subject_id", None)

        # get data for a specific chronofile? This is for STE downloader
        request_subject_chronofile = self.request.GET.get("subject_chronofile", None)

        request_source_provider = self.request.GET.get("source_provider", None)

        # get current status? or historical observations
        get_current = parse_bool(self.request.GET.get("current_status", "false"))

        # This call will embed a in order manufactured serial number per returned row
        #  do we start at 0 or some other number? This is for STE downloader
        record_serial_base = int(self.request.GET.get("record_serial_base", -1))

        # max number of records to return
        max_records = int(self.request.GET.get("max_records", -1))

        # Time range to query observation data according to user's permission
        max_days = 36500  # View All time days permission's number of days
        (lower, upper) = calculate_subject_view_window(self.request.user, max_days)
        if lower >= upper:
            raise PermissionDenied

        # if passed in bounds further restrict calculated ones for the user, use those
        upper = request_date_before if request_date_before is not None and request_date_before < upper else upper
        lower = request_date_after if request_date_after is not None and request_date_after > lower else lower

        fieldnames, fixtime_label, dloadtime_label = self._get_fieldnames(result_format, request_subject_id)

        # JSON format cannot be streamed - must return full list
        if result_format != "csv":
            csv_data = []
            if get_current:
                csv_data = list(
                    self._generate_current_status_rows(
                        max_records,
                        request_subject_id,
                        request_subject_chronofile,
                        request_source_provider,
                        result_format,
                        fixtime_label,
                        dloadtime_label,
                        record_serial_base,
                    )
                )
            else:
                csv_data = list(
                    self._generate_observation_rows(
                        filter_flag,
                        lower,
                        upper,
                        max_records,
                        request_subject_id,
                        request_subject_chronofile,
                        request_source_provider,
                        result_format,
                        fixtime_label,
                        dloadtime_label,
                        record_serial_base,
                    )
                )
            return Response(csv_data)

        # CSV format - use streaming response
        timestamp = current_tz.localize(datetime.datetime.utcnow())
        download_filename = f'Tracking Data {timestamp.strftime("%Y-%m-%d")}.csv'

        if get_current:
            row_generator = self._generate_current_status_rows(
                max_records,
                request_subject_id,
                request_subject_chronofile,
                request_source_provider,
                result_format,
                fixtime_label,
                dloadtime_label,
                record_serial_base,
            )
        else:
            row_generator = self._generate_observation_rows(
                filter_flag,
                lower,
                upper,
                max_records,
                request_subject_id,
                request_subject_chronofile,
                request_source_provider,
                result_format,
                fixtime_label,
                dloadtime_label,
                record_serial_base,
            )

        return StreamingCSVResponse(
            row_generator=row_generator,
            fieldnames=fieldnames,
            filename=download_filename,
        )

    def get_csv_observation_data(
        self, cur_record_serial, dloadtime_label, fixtime_label, result_format, item, subject_id, subject_chronofile
    ):
        recorded_at = item["recorded_at"].astimezone(current_tz) if result_format == "csv" else item["recorded_at"]
        created_at = item["created_at"].astimezone(current_tz) if result_format == "csv" else item["created_at"]

        request_key = "chronofile"
        if subject_id:
            request_key, value = "subject_id", subject_id
        elif subject_chronofile:
            value = subject_chronofile
        else:
            value = item["subjectsource_additional"].get("chronofile", "") if item["subjectsource_additional"] else ""

        collar_id = item["collar_id"]
        data = {
            "observation_id": item["id"],
            "lat": item["location"].y,
            "lon": item["location"].x,
            "height": item["location"].z,
            request_key: value,
            "collar_id": collar_id,
            "recordserial": cur_record_serial,
            fixtime_label: (
                recorded_at.strftime("%m/%d/%Y %H:%M:%S") if result_format == "csv" else recorded_at.isoformat()
            ),
            dloadtime_label: (
                created_at.strftime("%m/%d/%Y %H:%M:%S") if result_format == "csv" else created_at.isoformat()
            ),
            "temp": self.get_temperature(item),
            "voltage": self.get_voltage(item),
            "activity": self.get_attribute(item, "activity"),
            "activity_label": self.get_attribute(item, "activity_label"),
            "subject_name": item.get("name"),
        }
        return data

    @staticmethod
    def get_temperature(item):
        additional = item.get("additional")
        if additional:
            return additional.get("temp") or additional.get("temperature", 0)
        return 0

    @staticmethod
    def get_voltage(item):
        additional = item.get("additional")
        if additional:
            return additional.get("voltage") or additional.get("battery") or additional.get("batt", 0)
        return 0

    @staticmethod
    def get_attribute(item, key):
        additional = item.get("additional")
        if additional:
            return additional.get(key)
        return None

    def get_subject_trackdata_queryset(self, filter_flag, lower, subject, upper, max_records):
        if hasattr(subject, "subjectsource_id"):
            qs = Observation.objects.get_subjectsource_observations(
                subject.subjectsource_id, lower, upper, max_records, filter_flag=filter_flag, order_by="recorded_at"
            )
        else:
            # we can't update this to use get_subject_observations_partitioned because of the annotations being applied
            qs = Observation.objects.get_subject_observations(
                subject, lower, upper, max_records, filter_flag=filter_flag, order_by="recorded_at"
            )
        qs = qs.annotate(
            subjectsource_additional=F("source__subjectsource__additional"),
            collar_id=F("source__manufacturer_id"),
            subject_name=F("source__subjectsource__subject__name"),
        )
        return qs

    def get_subject_status_queryset(self, max_records, subject_id=None, chronofile=None, source_provider=None):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        min_age_days = get_minimum_allowed_age(self.request.user) or 0

        qs = SubjectStatus.objects.filter(delay_hours=min_age_days * 24).filter(
            subject__subjectsource__assigned_range__contains=now
        )
        if subject_id:
            qs = qs.filter(subject__id=subject_id)
        elif source_provider:
            qs = qs.filter(subject__subjectsource__source__provider__provider_key=source_provider)
        elif chronofile:
            qs = qs.filter(subject__subjectsource__additional__chronofile=int(chronofile))
        else:
            qs = qs.filter(subject__subjectsource__additional__chronofile__isnull=False)

        qs = qs.annotate(
            subjectsource_additional=F("subject__subjectsource__additional"),
            collar_id=F("subject__subjectsource__source__manufacturer_id"),
            subject_name=F("subject__name"),
        ).values()
        if max_records > 0:
            qs = qs[:max_records]
        return qs.values()


class TrackingMetaDataExportView(APIView):
    permission_classes = (
        UserCanExportDataPermission,
        StandardObjectPermissions,
    )

    # schema = InactiveSubjectsViewSchema()

    def _get_headers(self, output_format):
        """Get CSV headers with timezone-aware date column names."""
        data_starts = "data_starts ({})".format(tz_offset) if output_format != "json" else "data_starts"
        data_stops = "data_stops ({})".format(tz_offset) if output_format != "json" else "data_stops"
        return [
            "chronofile",
            "collar_type",
            "collar_id",
            "active",
            "datasource",
            "frequency",
            "animal_id",
            "name",
            "species",
            "subtype",
            "groups",
            data_starts,
            data_stops,
            "date_off_or_removed",
            "comments",
            "predicted_expiry",
            "rgb",
            "sex",
            "gmt",
            "data_status",
            "data_starts_source",
            "data_stops_source",
            "data_stops_reason",
            "collar_status",
            "collar_model",
            "has_acc_data",
            "data_owners",
            "region",
            "country",
            "subject_id",
            "source_id",
            "subjectsource_id",
            "external_id",
            "external_name",
        ]

    def _build_subject_groups_lookup(self, subject_ids):
        """
        Build a lookup dict mapping subject_id -> comma-separated group names.
        This eliminates the N+1 query problem by fetching all groups in one query.
        """
        from django.contrib.postgres.aggregates import StringAgg

        # Get all subject-group relationships in one query
        subject_groups_qs = (
            SubjectGroup.objects.filter(subjects__id__in=subject_ids)
            .values("subjects__id")
            .annotate(group_names=StringAgg("name", delimiter=","))
        )

        return {str(item["subjects__id"]): item["group_names"] for item in subject_groups_qs}

    def _get_annotated_queryset(self):
        """Get the base queryset with all necessary annotations."""
        subjects = self.get_queryset()
        return (
            subjects.select_related("subject_subtype")
            .annotate(subjectsource_additional=F("subjectsource__additional"))
            .annotate(source_model_name=F("subjectsource__source__model_name"))
            .annotate(source_manufacturer_id=F("subjectsource__source__manufacturer_id"))
            .annotate(subjectsource_assigned_range=F("subjectsource__assigned_range"))
            .annotate(source_additional=F("subjectsource__source__additional"))
            .annotate(source_id=F("subjectsource__source__id"))
            .annotate(subjectsource_id=F("subjectsource__id"))
        )

    def _transform_subject_to_row(self, subject, subject_groups_lookup, output_format, data_starts_key, data_stops_key):
        """Transform a subject into a CSV row dictionary."""
        subjectsource_additional = subject.subjectsource_additional or {}

        source_details = {
            "name": subject.name,
            "species": subject.additional.get("species", ""),
            "rgb": subject.additional.get("rgb", ""),
            "sex": subject.additional.get("sex", ""),
            "region": subject.additional.get("region", ""),
            "active": subject.is_active,
            "country": subject.additional.get("country", ""),
            "subtype": subject.subject_subtype.display if subject.subject_subtype else "",
            "groups": subject_groups_lookup.get(str(subject.id), ""),
            "subject_id": subject.id,
            "animal_id": subject.additional.get("tm_animal_id", ""),
            "external_id": subject.additional.get("external_id", ""),
            "external_name": subject.additional.get("external_name", ""),
        }

        if subject.source_additional is not None:
            lower = subject.subjectsource_assigned_range.lower
            upper = subject.subjectsource_assigned_range.upper
            try:
                if output_format != "json":
                    if lower != datetime.datetime(datetime.MINYEAR, 1, 1, tzinfo=pytz.utc):
                        lower = lower.astimezone(current_tz)
                    if upper != datetime.datetime(datetime.MAXYEAR, 12, 31, tzinfo=pytz.utc):
                        upper = upper.astimezone(current_tz)
            except Exception as exc:
                logger.debug(
                    "Failed to convert subjectsource_assigned_range to current timezone for subject %s: %s",
                    getattr(subject, "id", None),
                    exc,
                )

            source_details.update(
                {
                    "chronofile": subjectsource_additional.get("chronofile", None),
                    "collar_type": subject.source_model_name,
                    "collar_id": subject.source_manufacturer_id,
                    "datasource": subject.source_additional.get("datasource", ""),
                    "frequency": subject.source_additional.get("frequency", 0.0),
                    data_starts_key: (
                        lower.strftime("%m/%d/%Y %H:%M:%S") if output_format != "json" else lower.isoformat()
                    ),
                    data_stops_key: (
                        upper.strftime("%m/%d/%Y %H:%M:%S") if output_format != "json" else upper.isoformat()
                    ),
                    "comments": subjectsource_additional.get("comments", ""),
                    "predicted_expiry": subject.source_additional.get("predicted_expiry", ""),
                    "data_status": subjectsource_additional.get("data_status", ""),
                    "data_starts_source": subjectsource_additional.get("data_starts_source", ""),
                    "data_stops_source": subjectsource_additional.get("data_stops_source", ""),
                    "data_stops_reason": subjectsource_additional.get("data_stops_reason", ""),
                    "date_off_or_removed": subjectsource_additional.get("date_off_or_removed", ""),
                    "collar_status": subject.source_additional.get("collar_status", ""),
                    "collar_model": subject.source_additional.get("collar_model", ""),
                    "has_acc_data": subject.source_additional.get("has_acc_data", ""),
                    "data_owners": subject.source_additional.get("data_owners", ""),
                    "source_id": subject.source_id,
                    "subjectsource_id": subject.subjectsource_id,
                }
            )

        return source_details

    def _generate_rows(self, output_format):
        """
        Generator that yields CSV rows for streaming response.
        Fixes N+1 query by pre-fetching subject groups.
        """
        headers = self._get_headers(output_format)
        data_starts_key = headers[11]  # data_starts column
        data_stops_key = headers[12]  # data_stops column

        subjects = self._get_annotated_queryset()

        # Reuse the same queryset for IDs - Django evaluates lazily so this is safe
        subject_ids = list(subjects.values_list("id", flat=True))
        subject_groups_lookup = self._build_subject_groups_lookup(subject_ids)

        # Track seen subjectsources to avoid duplicates
        seen_subjectsources = set()

        for subject in subjects.iterator(chunk_size=2000):
            if subject.subjectsource_id in seen_subjectsources:
                continue
            seen_subjectsources.add(subject.subjectsource_id)

            try:
                yield self._transform_subject_to_row(
                    subject, subject_groups_lookup, output_format, data_starts_key, data_stops_key
                )
            except Exception as error:
                logger.exception(
                    "Failed to transform subject %s to CSV row: %s", getattr(subject, "id", None), error
                )
                continue

    def get_source_details(self, output_format):
        """
        Gather required details for each Subject/Source combination.
        Used for JSON format which requires a complete list.
        :return: Tuple of (list of dictionaries, headers list)
        """
        headers = self._get_headers(output_format)
        tracking_metadata = list(self._generate_rows(output_format))
        return tracking_metadata, headers

    def get(self, request, *args, **kwargs):
        from utils.csv_streaming import StreamingCSVResponse

        local_tz = pytz.timezone(timezone.get_current_timezone_name())
        timestamp = local_tz.localize(datetime.datetime.utcnow())
        output_format = self.request.GET.get("format", "").lower()

        # JSON format cannot be streamed - return full response
        if output_format == "json":
            tracking_metadata, headers = self.get_source_details(output_format)
            return HttpResponse(
                json.dumps({"metadata": tracking_metadata}, cls=DjangoJSONEncoder),
                content_type="application/json",
                status=status.HTTP_200_OK,
            )

        # CSV format - use streaming response
        headers = self._get_headers(output_format)
        download_filename = f'Tracking Meta Data Export {timestamp.strftime("%Y-%m-%d")}.csv'

        return StreamingCSVResponse(
            row_generator=self._generate_rows(output_format),
            fieldnames=headers,
            filename=download_filename,
        )

    def get_queryset(self):
        # Get user accessible active subjects.
        queryset = Subject.objects.all()
        # To include inactive subjects in trackingmetadata report
        queryset = check_to_include_inactive_subjects(self.request, queryset)
        queryset = queryset.by_user_subjects_not_distinct(self.request.user)
        return queryset


class GPXFileUploadView(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = GPXTrackFileUploadSerializer

    def create(self, request, *args, **kwargs):
        if not self.request.user.has_perm("observations.add_observation"):
            raise PermissionDenied
        source_id = kwargs.get("id")
        get_object_or_404(Source, id=source_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)

        inmemory_file = validated_data.get("gpx_file")
        filename = self.save_in_defaultstorage(inmemory_file)
        async_result = self.get_async_result(filename, source_id)
        data = self.create_data(request, inmemory_file, source_id, async_result)
        return Response(data, status=status.HTTP_201_CREATED)

    @staticmethod
    def save_in_defaultstorage(inmemory_file):
        file_path = f"{GPX_FILES_FOLDER}/{inmemory_file.name}"
        return default_storage.save(file_path, inmemory_file)

    @staticmethod
    def get_async_result(file, source_id):
        try:
            kwargs = {"domain": get_tenant_settings().domain} if features.tms.is_on() else {}
            async_result = process_gpxdata_api.apply_async(args=(file, source_id), kwargs=kwargs)
        except exceptions.OperationalError as exc:
            raise ValidationError({"error_message": exc})
        else:
            return async_result

    @staticmethod
    def create_data(request, file, source_id, async_result):
        status_url = add_base_url(request, reverse("gpx-status", kwargs={"id": source_id, "task_id": async_result.id}))
        data = dict(
            source_id=source_id,
            filename=file.name,
            filesize_bytes=file.size,
            process_status=dict(
                task_info=async_result.info,
                task_id=async_result.id,
                task_success=async_result.successful(),
                task_failed=async_result.failed(),
                task_url=status_url,
            ),
        )
        return data


class GPXTaskStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        # status: Pending means task is waiting for execution or unknown.
        # Any task id that is unknown is implied to be in pending state.
        task_id = self.kwargs.get("task_id")
        asyncResult = celery.app.AsyncResult(task_id)
        result = (
            dict(error_msg=asyncResult.result.message)
            if isinstance(asyncResult.result, Exception)
            else asyncResult.result
        )

        data = dict(
            task_result=result,
            task_status=asyncResult.status.title(),
            task_success=asyncResult.successful(),
            task_failed=asyncResult.failed(),
        )
        if asyncResult.status != "STARTED":
            # Release the resources whenever AsyncResult instance is called.
            asyncResult.forget()
        return Response(data, status=status.HTTP_200_OK)


def get_user_messages(user):
    # Get messages a user has access to
    user_subjects = Subject.objects.filter(is_active=True).by_user_subjects(user)
    user_subject_ids = [subj.id for subj in user_subjects]
    messages = Message.objects.filter(Q(sender_id__in=user_subject_ids) | Q(receiver_id__in=user_subject_ids))
    return messages


class MessagesSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        operation["parameters"] = operation.get("parameters", [])
        if self.method == "GET":
            query_params = [
                {"name": "subject_id", "in": "query", "description": "Get messages of this subject."},
                {"name": "source_id", "in": "query", "description": "Get messages of this device/source"},
                {"name": "read", "in": "query", "description": "Get read/unread messages"},
                {"name": "recent_message", "in": "query", "description": "Number of recent messages"},
                {"name": "since", "in": "query", "description": "Include messages since this timestamp"},
                {"name": "until", "in": "query", "description": "Include messages older than this timestamp"},
            ]
            operation["parameters"].extend(query_params)

        elif self.method == "POST":
            query_params = [
                {"name": "subject_id", "in": "query", "description": "Post messages to this subject."},
                {"name": "source_id", "in": "query", "description": "Post Messages to this device/source"},
                {
                    "name": "manufacturer_id",
                    "in": "query",
                    "description": "Post Messages from a device of this manufacturer id.",
                },
            ]
            operation["parameters"].extend(query_params)

        return operation


class MessagesView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = (StandardObjectPermissions,)
    pagination_class = StandardResultsSetPagination
    schema = MessagesSchema()

    def _get_recent_messages(self, messages: QuerySet, number_recent_msg: int) -> RawQuerySet:
        sender = {"partition_by": F("sender_id"), "order_by": [F("message_time").desc()]}
        receiver = {"partition_by": F("receiver_id"), "order_by": [F("message_time").desc()]}

        messages = messages.annotate(
            rn_sender=Window(expression=RowNumber(), **sender),
            rn_receiver=Window(expression=RowNumber(), **receiver),
        )
        sql, params = messages.query.sql_with_params()
        messages = Message.objects.raw(
            f"""
            select * from ({sql}) msgs where rn_sender<= %s or rn_receiver <= %s
            """,
            params=[*params, number_recent_msg, number_recent_msg],
        )
        return messages

    def get_queryset(self):
        query_params = self.request.query_params
        queryset = get_user_messages(self.request.user)

        if since := query_params.get("since", None):
            since = dateparse(since)

        if until := query_params.get("until", None):
            until = dateparse(until)

        subject_id = query_params.get("subject_id")
        source_id = query_params.get("source_id")
        read = query_params.get("read")
        number_recent_msg = query_params.get("recent_message")

        if subject_id:
            # Accepting a list i.e : ?subject_id=id1, id2, id2
            subject_ids = [x.strip(" ") for x in subject_id.split(",")]
            queryset = queryset.by_subject_ids(subject_ids)
        if source_id:
            queryset = queryset.by_source_id(source_id)
        if read is not None:
            queryset = queryset.by_read(parse_bool(read))

        if number_recent_msg and (since or until):
            raise ValidationError("recent_message query param cannot be used with since or until query params")

        if not number_recent_msg and not since and not until:
            # Default to last 30 days until UI is updated to handle pagination
            since = datetime.datetime.now(tz=pytz.utc) - datetime.timedelta(days=30)

        queryset = queryset.by_date_range(since, until).select_related("device")

        if number_recent_msg and number_recent_msg.isdigit():
            return self._get_recent_messages(messages=queryset, number_recent_msg=number_recent_msg)

        return queryset

    def post(self, request, *args, **kwargs):
        data = request.data

        if data.get("bulk_read"):
            # Handle bulk reading of messages
            ids, read = data.get("ids"), data.get("read", True)
            ids = [ids] if isinstance(ids, str) else ids

            queryset = get_user_messages(request.user)
            ids = list(set(ids).intersection({str(k.id) for k in queryset}))

            msgs = queryset.filter(id__in=ids)
            msgs.update(read=read, updated_at=timezone.now())

            read_state = "read" if read else "unread"
            return Response(f"{len(ids)} messages successfully updated to {read_state}", status=status.HTTP_200_OK)

        return self.create(request, *args, **kwargs)

    def save_message(self, request, data):
        serializer = self.serializer_class(data=data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()
        return serializer.data

    def create(self, request, *args, **kwargs):
        data = request.data
        message_type = data.get("message_type", "outbox")
        data["message_time"] = data.get("message_time", datetime.datetime.now(tz=pytz.utc).isoformat())

        qparams = self.request.query_params
        if message_type == "inbox":
            # Handle Inbox messages

            manufacturer_id = qparams.get("manufacturer_id")
            if not manufacturer_id:
                return Response(
                    {"Error": "Manufacturer Id param has to be provided for an inbox message"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            dt = parse_datetime(data["message_time"])
            for subject_source in SubjectSource.objects.filter(
                source__manufacturer_id=manufacturer_id, assigned_range__contains=dt
            ).distinct("subject"):
                data["sender"] = {"content_type": "observations.subject", "id": subject_source.subject.id}
                data["device"] = str(subject_source.source.id)
                # update incoming message status to received.
                data["status"] = RECEIVED
                ser_data = self.save_message(request, data)
        else:
            # Handle Outbox messages
            subject_id = qparams.get("subject_id").strip()
            source_id = qparams.get("source_id").strip()

            if not (subject_id and source_id):
                return Response(
                    {"Error": "Source_id and subject_id params needed for an outbox message"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Set logged in user as the sender
            data["sender"] = {"content_type": "accounts.user", "id": request.user.id}
            data["receiver"] = {"content_type": "observations.subject", "id": subject_id}
            data["device"] = source_id

            ser_data = self.save_message(request, data)

            message_id, user_email = ser_data.get("id"), request.user.email
            kwargs = {"domain": get_tenant_settings().domain} if features.tms.is_on() else {}
            handle_outbox_message.apply_async(args=(message_id, user_email), kwargs=kwargs)

        headers = self.get_success_headers(ser_data)
        return Response(ser_data, status=status.HTTP_201_CREATED, headers=headers)


class MessageView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    serializer_class = MessageSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return get_user_messages(self.request.user)


class AnnouncementsView(generics.ListCreateAPIView):
    serializer_class = AnnouncementSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = Announcement.objects.all().order_by_announcement_at()

        query_params = self.request.query_params
        is_read = query_params.get("is_read")
        user = self.request.user

        if is_read is not None:
            queryset = queryset.by_read(parse_bool(is_read), user)

        return queryset

    def post(self, request, *args, **kwargs):
        query_params = self.request.query_params
        read = query_params.get("read")
        if not read:
            raise ParseError(detail=" Malformed request. Query parameter 'read' is required.")

        data = dict(news_ids=[x.strip() for x in read.split(",")])
        serializer = ReadAnnouncementSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        queryset = Announcement.objects.filter(pk__in=serializer.data.get("news_ids"))
        [q.related_users.add(request.user) for q in queryset]

        context = dict(request=self.request)
        response = self.serializer_class(queryset, many=True, context=context)
        return Response(response.data, status=status.HTTP_200_OK)


class SubjectSourceAssignmentSchema(CustomSchema):
    def get_operation(self, *args, **kwargs):
        operation = super().get_operation(*args, **kwargs)
        if self.method == "GET":
            query_params = [
                {"name": "subjects", "in": "query", "description": "A comma-delimited list of Subject IDs."},
                {"name": "sources", "in": "query", "description": "A comma-delimited list of Source IDs."},
            ]
            operation["parameters"] = operation.get("parameters", [])
            operation["parameters"].extend(query_params)

        return operation


class SubjectSourcesAssignmentView(generics.ListAPIView):
    permission_classes = (StandardObjectPermissions,)
    serializer_class = SubjectSourceSerializer
    pagination_class = StandardResultsSetPagination
    schema = SubjectSourceAssignmentSchema()

    def get_queryset(self):
        query_params = self.request.query_params

        subjects_list = parse_comma(query_params.get("subjects"))
        sources_list = parse_comma(query_params.get("sources")) or []

        allowed = Subject.objects.by_user_subjects(self.request.user).values_list("id", flat=True)

        # First get subject-sources user has access to.
        queryset = SubjectSource.objects.filter(subject_id__in=allowed)

        if subjects_list and sources_list:
            queryset = queryset.filter(
                Q(subject_id__in=set(allowed) & set(subjects_list)) | Q(source_id__in=sources_list)
            )
        elif subjects_list:
            queryset = queryset.filter(subject_id__in=set(allowed) & set(subjects_list))
        elif sources_list:
            queryset = queryset.filter(source_id__in=sources_list)
        return queryset


__all__ = [
    "AnnouncementsView",
    "FlattenObservationsView",
    "get_subjects_with_observations_in_daterange",
    "GPXFileUploadView",
    "GPXTaskStatusView",
    "KmlRootView",
    "KmlSubjectView",
    "KmlSubjectsView",
    "MessageView",
    "MessagesView",
    "ObservationView",
    "ObservationsView",
    "RegionSubjectsView",
    "RegionView",
    "RegionsView",
    "SourceGroupView",
    "SourceGroupsView",
    "SourceProvidersViewPartial",
    "SourceSubjectsView",
    "SourceView",
    "SourcesView",
    "SubjectGroupView",
    "SubjectGroupsView",
    "SubjectGroupSubjectsView",
    "SubjectSourceTrackView",
    "SubjectSourceView",
    "SubjectSourcesAssignmentView",
    "SubjectSourcesView",
    "SubjectStatusView",
    "SubjectSubjectSourcesView",
    "SubjectTracksView",
    "SubjectView",
    "SubjectsGeoJsonView",
    "SubjectsView",
    "TrackingDataCsvView",
    "TrackingMetaDataExportView",
]
