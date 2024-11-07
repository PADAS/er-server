import json
import logging

import dateutil.parser as dateparser

from django.db.models import Q
from django.db.models.query import QuerySet
from rest_framework.exceptions import ParseError
from rest_framework.filters import BaseFilterBackend
from rest_framework.request import Request
from rest_framework.views import APIView

from activity.models import EventCategory
from activity.views.exceptions import BadRequestAPIException
from observations.models import Subject
from utils.categories import (
    get_categories_and_geo_categories,
    make_eventcategory_permission_codename,
)
from utils.json import parse_bool

logger = logging.getLogger(__name__)


class EventSubjectsFilter(BaseFilterBackend):

    def filter_queryset(self, request: Request, queryset: QuerySet, view: APIView) -> QuerySet:
        user_subjects = Subject.objects.by_user_subjects(request.user).values_list("id", flat=True)
        queryset = queryset.filter(Q(related_subjects__isnull=True) | Q(related_subjects__in=user_subjects))

        return queryset


class EventPermissionsFilter(BaseFilterBackend):
    """
    Filter the list of events to what the user is allowed to view
    """

    #
    # TODO: Update this filter to use new category permisisons
    #

    def filter_queryset(self, request: Request, queryset: QuerySet, view: APIView) -> QuerySet:
        query_params = request.query_params
        user = request.user

        event_categories = query_params.getlist("event_category")

        if not event_categories:
            event_categories = EventCategory.get_category_keys()

        # Check user permissions for event categories
        allowed_event_categories = []
        for event_category in event_categories:
            permission_name = f"activity.{event_category}_read"
            geo_permission_name = f"activity.{make_eventcategory_permission_codename(event_category, 'view', True)}"
            if user.has_perm(permission_name) or user.has_perm(geo_permission_name):
                allowed_event_categories.append(event_category)

        if not allowed_event_categories:
            return queryset.none()
        queryset = queryset.by_category(allowed_event_categories)

        queryset = queryset.by_location(query_params.get("location", ""), user, get_categories_and_geo_categories(user))

        return queryset


class EventListFilter(BaseFilterBackend):

    def filter_queryset(self, request: Request, queryset: QuerySet, view: APIView) -> QuerySet:
        query_params = request.query_params

        # Filter events by especific event_ids
        event_ids = query_params.getlist("event_ids")
        if event_ids:
            queryset = queryset.filter(id__in=event_ids)

        # Filter events by state
        state = query_params.getlist("state")
        if state:
            queryset = queryset.by_state(state)

        # Filter events by event_type
        event_type = query_params.getlist("event_type")
        if event_type:
            queryset = queryset.by_event_type(event_type)

        # Filter events by updated_since
        updated_since = query_params.get("updated_since", None)
        if updated_since:
            try:
                updated_since = dateparser.parse(updated_since)
            except ValueError:
                raise ParseError(detail=f"Invalid value for 'updated_since' = '{updated_since}'")
            queryset = queryset.updated_since(updated_since)

        # Filter events by is_collection XOR exclude_contained
        is_collection = query_params.get("is_collection", None)
        exclude_contained = query_params.get("exclude_contained", None)
        if is_collection and exclude_contained:
            raise BadRequestAPIException(detail="Invalid use of is_collection and exclude_contained in the same call")
        if is_collection:
            queryset = queryset.by_is_collection(parse_bool(is_collection))
        if exclude_contained:
            queryset = queryset.by_exclude_contained(parse_bool(exclude_contained))

        # Filter events by bounding box
        bbox = query_params.get("bbox", None)
        if bbox:
            try:
                bbox = [float(v) for v in bbox.split(",")]
            except ValueError:
                raise ParseError(detail="Invalid bbox param")
            if len(bbox) != 4:
                raise ParseError(detail="Invalid bbox param")
            queryset = queryset.by_bbox(bbox)

        # Filter events by json filter specification
        event_filter = query_params.get("filter", None)
        if event_filter:
            try:
                event_filter = json.loads(event_filter)
                queryset = queryset.by_event_filter(event_filter)
            except json.JSONDecodeError as e:
                logger.exception("Invalid filter expression. filter=%s", event_filter)
                raise ParseError(detail=f"Invalid filter expression. 'filter' = '{event_filter}'") from e

        return queryset
