import datetime
import json
import logging
import re
import uuid
from enum import Enum
from itertools import chain
from operator import attrgetter, itemgetter

import phonenumbers
import pytz
from django_multitenant.fields import TenantForeignKey, TenantOneToOneField
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from versatileimagefield.fields import VersatileImageField

import django.utils
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.db.models import QuerySet
from django.contrib.gis.db.models.functions import Distance as D
from django.contrib.gis.geos import Polygon
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.search import SearchQuery, SearchVectorField
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator
from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    Exists,
    F,
    Index,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    UniqueConstraint,
    Value,
    When,
)
from django.db.models.functions import Cast, Lower
from django.utils import dateparse, timezone
from django.utils.encoding import force_str
from django.utils.translation import gettext_lazy as _

from accounts.models.permissionset import PermissionSet
from accounts.system_users import DELETED_SENTINEL_USER
from core.mixins import SerialNumberModelMixin
from core.models import DASTenant, TenantSingletonModel, TimestampedModel, UUIDModel
from core.utils import static_image_finder
from observations.models import Subject, SubjectGroup, SubjectStatus
from observations.utils import dateparse as dparse
from observations.utils import is_banned
from revision.manager import (
    CompoundUserField,
    Revision,
    RevisionAdapter,
    RevisionMixin,
    relation_deleted,
)
from utils.gis import convert_to_point, get_circle_polygon_from_point
from utils.html import clean_user_text
from utils.json import parse_bool
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager
from utils.rank import RankModelMixin
from utils.tenant import get_tenant_settings
from utils.tenant.models import TenantThroughModel

from .constants import (
    PRI_BLACK,
    PRI_IMPORTANT,
    PRI_NONE,
    PRI_REFERENCE,
    PRI_URGENT,
    PRIORITY_CHOICES,
    SC_ACTIVE,
    SC_NEW,
    SC_RESOLVED,
    STATE_CHOICES,
)

logger = logging.getLogger(__name__)


DEFAULT_EVENT_PATROL_ICON_ID = "generic_rep"


def get_sentinel_user():
    """
    This is no longer used by the application, but it is still referenced within some migrations.
    :return: a default user
    """
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=DELETED_SENTINEL_USER,
        defaults=dict(
            last_name="account",
            first_name="deleted",
            is_active=False,
            is_system=True,
            password=User.objects.make_random_password(),
        ),
    )
    return user


class CommunityManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)

    def create_member(self, **values):
        return self.create(**values)


class Community(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommunityManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Event Reporters")
        verbose_name_plural = _("Event Reporters")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.name


class EventBaseManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_value(self, value):
        return self.get(value=value)

    def all_sort(self):
        # default order ordernum
        result = self.order_by("ordernum")

        return result

    def get_by_natural_key(self, value):
        return self.get(value=value)


class EventClass(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40)
    display = models.CharField(max_length=100, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventBaseManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "value"], name="%(class)s_val_idx")]

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class EventFactor(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=40)
    display = models.CharField(max_length=100, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventBaseManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "value"], name="%(class)s_val_idx")]

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class EventCategory(TenantModelMixin, TimestampedModel, RankModelMixin):

    CATEGORIES_CACHE_KEY = "active_categories"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # the value field is used as part of the codename of a set of permissions created for each EventCategory
    # this limits us to the size of the EventCategory value field as the codename field has a limit of 100 chars
    # we add some prefixs and suffixes when generating the codename, effectively limiting us to 67 chars here
    value = models.CharField(max_length=67)
    display = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    flag = models.CharField(max_length=40, default="user", choices=(("user", "User"), ("system", "System")))

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    objects = EventBaseManager()

    class Meta:
        verbose_name = _("Event Category")
        verbose_name_plural = _("Event Categories")
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [
            Index(fields=["das_tenant", "value"], name="%(class)s_val_idx"),
            Index(fields=["das_tenant", "ordernum"], name="%(class)s_ordernum_idx"),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.display or self.value

    @classmethod
    def get_active_categories(cls):
        active_categories = cache.get(cls.CATEGORIES_CACHE_KEY)
        if active_categories is None:
            active_categories = list(cls.objects.filter(is_active=True))
            cache.set(cls.CATEGORIES_CACHE_KEY, active_categories, 5 * 60)

        return active_categories

    @classmethod
    def get_category_keys(cls):
        return [category.value for category in cls.get_active_categories()]

    def natural_key(self):
        return (self.value,)

    @property
    def auto_permissionset_name(self):
        return _("View {} Event Permissions").format(self.display)

    @property
    def auto_geographic_permission_set_name(self):
        return _(f"View {self.display} Event Geographic Permissions")


class FilterFieldMixin(object):
    def filter_field(self, field_name, field_data):
        if field_data is None:
            return self

        if isinstance(field_data, (list, tuple)):
            field_q = None
            for value in field_data:
                field_q = field_q | models.Q(**{field_name: value}) if field_q else models.Q(**{field_name: value})
        else:
            field_q = models.Q(**{field_name: field_data})
        return self.filter(field_q)


class EventTypeFilteringQuerySet(models.QuerySet, FilterFieldMixin):
    def by_category(self, category):
        return self.filter_field("category__value", category)

    def by_including_inactive_categories(self, include_inactive):
        if parse_bool(include_inactive):
            return self.filter_field("category__is_active", True)

        return self

    def by_is_collection(self, value):
        return self.filter_field("is_collection", value)

    def by_event_type(self, event_types):
        if isinstance(event_types, str):
            values = [x.strip() for x in event_types.split(",")]
        return self.filter(value__in=values)


class EventTypeManager(TenantManagerMixin, models.Manager.from_queryset(EventTypeFilteringQuerySet)):
    use_in_migrations = True

    def create_type(self, **values):
        return self.create(**values)

    def get_by_value(self, value):
        return self.get(value=value)

    def all_sort(self):
        # default order ordernum
        result = self.order_by("ordernum")
        return result

    def get_by_natural_key(self, value):
        return self.get(value=value)


class EventType(TenantModelMixin, RankModelMixin, TimestampedModel, RevisionMixin):

    class VersionChoices(models.TextChoices):
        VERSION_1 = "1"
        VERSION_2 = "2"

    class GeometryTypesChoices(models.TextChoices):
        POINT = "Point"
        POLYGON = "Polygon"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(
        max_length=255,
        validators=[
            RegexValidator(
                regex="^[A-Za-z0-9-_]*$",
                message=(
                    "An invalid character was detected in the Event type Value field. "
                    "Supported characters are: Letters a-z (lowercase), Numbers 0-9 and Underscore"
                ),
            )
        ],
    )
    display = models.CharField(max_length=255, blank=True)
    category = TenantForeignKey(EventCategory, null=True, on_delete=models.PROTECT)
    default_priority = models.PositiveSmallIntegerField(default=PRI_NONE, choices=PRIORITY_CHOICES)
    default_state = models.CharField(default=SC_NEW, choices=STATE_CHOICES, max_length=20)
    icon = models.CharField(max_length=100, blank=True, null=True)
    schema = models.TextField(
        blank=True,
        default="""{
                "schema":
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "title": "Empty Event Schema",
                    "type": "object",
                    "properties": {}
                },
                "definition": []
                }""",
    )
    is_collection = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    readonly = models.BooleanField(default=False)
    auto_resolve = models.BooleanField(default=False)
    # Specify integer of hour(s).
    resolve_time = models.PositiveSmallIntegerField(blank=True, null=True)
    geometry_type = models.CharField(
        choices=GeometryTypesChoices.choices, default=GeometryTypesChoices.POINT, max_length=20
    )
    version = models.CharField(max_length=1, default=VersionChoices.VERSION_1, choices=VersionChoices.choices)

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    objects = EventTypeManager()
    revision = Revision(user_field_class=CompoundUserField)

    class Meta:
        verbose_name = _("Event Type")
        verbose_name_plural = _("Event Types")
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(
                check=Q(auto_resolve=False, resolve_time__isnull=True)
                | Q(auto_resolve=True, resolve_time__isnull=False),
                name="auto_resolve_constraint",
            ),
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            ),
        ]

        indexes = [
            Index(fields=["das_tenant", "geometry_type"]),
            Index(fields=["das_tenant", "is_active"]),
            Index(fields=["das_tenant", "is_collection"]),
            Index(fields=["das_tenant", "version"]),
            Index(fields=["das_tenant", "value"], name="%(app_label)s_%(class)s_val_idx"),
            Index(fields=["das_tenant", "ordernum"], name="%(class)s_ordernum_idx"),
        ]

    def __str__(self):
        return self.display or self.value

    def clean(self, *args, **kwargs):
        if not self.auto_resolve and self.resolve_time:
            raise ValidationError({"resolve_time": "'resolve_time' must be null if 'auto_resolve' is false."})
        elif self.auto_resolve and not self.resolve_time:
            raise ValidationError({"resolve_time": "'resolve_time' must be set if 'auto_resolve' is true."})

    def save(self, *args, **kwargs):
        self.full_clean()
        self.value = self.value.lower()
        return super().save(*args, **kwargs)

    def set_to_inactive(self):
        self.is_active = False
        self.save()

    def natural_key(self) -> tuple:
        return (self.value,)

    @property
    def icon_id(self) -> str:
        if not self.icon:
            if static_image_finder.get_marker_icon(
                chain([self.value], Event.generate_image_keys(self.value, PRI_BLACK, self.default_state))
            ):
                return self.value
            return DEFAULT_EVENT_PATROL_ICON_ID
        return self.icon

    @property
    def image_url(self) -> str:
        return Event.marker_icon(self.icon_id, PRI_BLACK, Event.SC_NEW)


def parse_date_range(val):
    lower, upper = (val.get("lower"), val.get("upper"))
    if lower is not None:
        lower = dateparse.parse_datetime(lower)
    if upper is not None:
        upper = dateparse.parse_datetime(upper)
    return lower, upper


class RefreshRecreateEventDetailViewQuery(models.QuerySet):
    def recreate(self, activity, task_mode):
        return self.create(
            task_mode=task_mode,
            started_at=datetime.datetime.now(tz=pytz.utc),
            performed_by=activity,
            maintenance_status="running",
        )

    def refresh(self, activity, task_mode):
        return self.create(task_mode=task_mode, started_at=datetime.datetime.now(tz=pytz.utc), performed_by=activity)

    def update_status(self, status):
        self.update(maintenance_status=status)

    def update_status_and_ended_at(self, status, error_details):
        self.update(maintenance_status=status, ended_at=datetime.datetime.now(tz=pytz.utc), error_details=error_details)


class RefreshRecreateEventDetailViewManager(
    TenantManagerMixin,
    models.Manager.from_queryset(
        RefreshRecreateEventDetailViewQuery,
    ),
):
    use_in_migrations = True


class RefreshRecreateEventDetailView(TenantModelMixin, UUIDModel):
    SUCCESS = "succeeded"
    SUCCESS_WARNING = "succeeded-warning"
    FAILED = "failed"
    REFRESH = "Refresh"
    RECREATE = "Recreate"
    RUNNING = "running"
    TASK_MODE = [(REFRESH, "refresh"), (RECREATE, "recreate")]
    performed_by = models.CharField(blank=True, null=True, max_length=255)
    task_mode = models.CharField(blank=True, null=True, max_length=255, choices=TASK_MODE)
    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    maintenance_status = models.CharField(max_length=255)
    error_details = models.JSONField("error details", default=list, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = RefreshRecreateEventDetailViewManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name_plural = "Refresh Data for Tableau"
        base_manager_name = "objects"
        default_manager_name = "objects"


class EventFilteringQuerySet(models.QuerySet, FilterFieldMixin):
    def all_sort(self, sort_by="-sort_at"):
        return self.order_by(sort_by)

    def by_bbox(self, bbox, last_days=None):
        geom = Polygon.from_bbox(bbox)
        events = self.filter(Q(location__within=geom) | Q(geometries__geometry__intersects=geom)).order_by(
            "-created_at"
        )
        if last_days:
            lt = timezone.now()
            gt = lt - last_days
            events = events.filter(created_at__range=(gt, lt))

        return events

    def by_state(self, state):
        return self.filter_field("state", state)

    def by_category(self, category):
        return self.filter_field("event_type__category__value", category)

    def by_event_type(self, event_type):
        return self.filter_field("event_type", event_type)

    def by_is_collection(self, value):
        return self.filter_field("event_type__is_collection", value)

    def updated_since(self, value):
        return self.filter_field("updated_at__gte", value)

    def by_exclude_contained(self, value):
        if not value:
            return self
        return self.exclude(in_relationship__type__value="contains")

    def by_location(self, location: str, user, categories_to_filter: dict):
        if user.is_superuser:
            return self
        queryset = self

        try:
            point = convert_to_point(location)
            radius = get_circle_polygon_from_point(location)
        except (TypeError, ValueError):
            point = None
            radius = None

        if point:
            queryset = queryset.annotate(distance=D("location", point, spheroid=True))

        filters = Q(event_type__category__value__in=categories_to_filter["categories"])

        if not is_banned(user) and point:
            filters = (
                Q(event_type__category__value__in=categories_to_filter["geo_categories"])
                & Q(location__isnull=False)
                & Q(distance__lt=get_tenant_settings().env_settings.geo_permission_radius_meters)
            )

            filters |= Q(geometries__geometry__intersects=radius) & Q(
                event_type__category__value__in=categories_to_filter["geo_categories"]
            )

        return queryset.filter(filters)

    def by_event_filter(self, filter):
        queryset = self

        if "event_filter_id" in filter:
            try:
                efilter = EventFilter.objects.get(id=filter.get("event_filter_id"))
                return self.by_event_filter(efilter.filter_spec)
            except EventFilter.DoesNotExist:
                # TODO: Handle this better.
                return Event.objects.none()

        if filter.get("text"):
            queryset = queryset.by_text_filter(filter.get("text"))

        if "date_range" in filter:
            lower, upper = parse_date_range(filter["date_range"])
            queryset = queryset.by_date_range(lower=lower, upper=upper)

        elif filter.get("duration"):
            duration = dateparse.parse_duration(filter.get("duration"))
            queryset = queryset.by_duration(duration)

        if filter.get("state"):
            queryset = queryset.filter(state__in=filter.get("state"))

        if filter.get("priority"):
            queryset = queryset.filter(priority__in=filter.get("priority"))

        if filter.get("event_category"):
            queryset = queryset.filter(event_type__category__id__in=filter.get("event_category"))

        if filter.get("event_type"):
            queryset = queryset.filter(event_type__id__in=filter.get("event_type"))

        if filter.get("reported_by"):
            queryset = queryset.filter(reported_by_id__in=filter.get("reported_by"))

        if filter.get("create_date"):
            lower, upper = parse_date_range(filter.get("create_date"))
            queryset = queryset.by_created_date(lower=lower, upper=upper)

        if filter.get("update_date"):
            lower, upper = parse_date_range(filter.get("update_date"))
            queryset = queryset.by_updated_date(lower=lower, upper=upper)

        return queryset

    def by_duration(self, duration):
        if duration:
            return self.filter(event_time__gt=(timezone.now() - duration))
        return self

    def by_date_range(self, lower=None, upper=None):
        if lower and upper:
            return self.filter(event_time__range=(lower, upper))
        elif lower:
            return self.filter(event_time__gte=lower)
        elif upper:
            return self.filter(event_time__lt=upper)

        return self

    def by_text_filter(self, search_text):
        search_text = search_text.strip()
        if not search_text:
            return self
        # Escape special characters that have meaning in PostgreSQL tsquery syntax
        # Special chars: & | ! ( ) < >
        # Remove or replace these characters to avoid syntax errors
        escaped_text = re.sub(r"[&|!()<>]", " ", search_text)
        # Split by whitespace and filter out empty strings
        words = [word for word in escaped_text.split() if word]
        if not words:
            return self
        ts_query = ":* & ".join(words) + ":*"
        search_query = SearchQuery(ts_query, search_type="raw")
        filter_query = (
            Q(tsvectormodel__tsvector_event=search_query)
            | Q(tsvectormodel__tsvector_event_note=search_query)
            | Q(serial_number__istartswith=search_text)
        )
        return self.filter(filter_query)

    def by_created_date(self, lower=None, upper=None):
        if lower and upper:
            return self.filter(created_at__range=(lower, upper))
        elif lower:
            return self.filter(created_at__gte=lower)
        elif upper:
            return self.filter(created_at__lt=upper)

        return self

    def by_updated_date(self, lower=None, upper=None):
        if lower and upper:
            return self.filter(updated_at__range=(lower, upper))
        elif lower:
            return self.filter(updated_at__gte=lower)
        elif upper:
            return self.filter(updated_at__lte=upper)


class EventManager(TenantManagerMixin, models.Manager.from_queryset(EventFilteringQuerySet)):
    use_in_migrations = True

    def create_event(self, **values):
        patrol_segments = values.pop("patrol_segments", None)
        event = self.create(**values)
        if patrol_segments:
            event.patrol_segments.set(patrol_segments)
        return event

    def get_reported_by(self, user=None):
        """Yield a tuple that is the provenance, users

        Args:
            user ([type], optional): user to authenticate against. Defaults to None.
        """
        for p in Event.PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(self.get_reported_by_for_provenance(provenance, user))
            yield (provenance, values)

    def get_reported_by_for_provenance(self, provenance, user=None):
        if Event.PC_STAFF == provenance:

            def get_staff():
                # First get all user accounts in the reported by permission
                # set, if it exists in the settings and the db
                try:
                    reported_by_users = PermissionSet.objects.get(id=settings.REPORTED_BY_PERMISSION_SET).user_set
                    for obj in reported_by_users.filter(is_active=True):
                        yield (obj.get_full_name().lower(), obj)
                except PermissionSet.DoesNotExist:
                    logger.warning("Someone has deleted the reported_by permission set")
                except AttributeError:
                    logger.warning("Reported by permission set not specified in settings")

                # We also want subjects who are staff (rangers are tracked as
                # subjects via their radio, but can report events
                staff_subject = Subject.objects.all().get_staff().by_is_active()

                # get subjects user has permission for.
                for obj in staff_subject.by_user_subjects(user) if user else staff_subject:
                    yield (obj.name.lower(), obj)

            for staff in sorted(get_staff(), key=itemgetter(0)):
                yield staff[1]

        elif Event.PC_COMMUNITY == provenance:
            for community in sorted(Community.objects.all(), key=attrgetter("name")):
                yield community

    def new_count(self):
        return self.new().count()

    def new(self):
        return self.filter(state=Event.SC_NEW)

    def get_related_patrol_ids(self, *, event=None):
        return [str(p["id"]) for p in Patrol.objects.filter(patrol_segment__event=event).values("id")]


class EventRelationshipType(TenantModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=50)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    symmetrical = models.BooleanField(default=False)

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    objects = EventBaseManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "value"], name="%(class)s_val_idx")]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.value


class EventRelationshipManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def add_relationship(self, from_event, to_event, type):
        try:
            ert = EventRelationshipType.objects.get(value=type)

            if not from_event.event_type.is_collection:
                raise ValidationError(
                    {"is_collection": ValidationError(_("Event is not a collection"), code="invalid")}
                )

        except EventRelationshipType.DoesNotExist as e:
            raise ValidationError(
                {"type": ValidationError(_("Invalid value for event relationship type."), code="invalid")}
            ) from e
        with transaction.atomic():
            new_relation, created = EventRelationship.objects.get_or_create(
                from_event=from_event, to_event=to_event, type=ert
            )
            if ert.symmetrical:
                rel, created = EventRelationship.objects.get_or_create(
                    from_event=to_event, to_event=from_event, type=ert
                )

        return new_relation

    def remove_relationship(self, from_event, to_event, type):
        try:
            ert = EventRelationshipType.objects.get(value=type)

        except EventRelationshipType.DoesNotExist as e:
            raise ValidationError(
                {
                    "event_relationship_type": ValidationError(
                        _("Invalid value for event_relationship_type"), code="invalid"
                    )
                }
            ) from e
        with transaction.atomic():
            result = EventRelationship.objects.filter(from_event=from_event, to_event=to_event, type=ert).delete()
            if ert.symmetrical:
                EventRelationship.objects.filter(from_event=to_event, to_event=from_event, type=ert).delete()

        return result


class EventFile(TenantModelMixin, TimestampedModel, RevisionMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event = TenantForeignKey("Event", related_name="files", related_query_name="file", on_delete=models.CASCADE)
    comment = models.TextField(blank=True, null=False, default="", verbose_name="Comment about the file.")
    relation_limits = models.Q(app_label="usercontent", model="filecontent") | models.Q(
        app_label="usercontent", model="imagefilecontent"
    )
    created_by = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_files",
        related_query_name="event_file",
    )
    # Generic foreign key to plugin
    usercontent_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=relation_limits)
    usercontent_id = models.UUIDField()
    usercontent = GenericForeignKey("usercontent_type", "usercontent_id")
    ordernum = models.SmallIntegerField(blank=True, null=True)
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        verbose_name = _("Event File")
        verbose_name_plural = _("Event Files")
        ordering = ["ordernum", "-updated_at"]
        base_manager_name = "objects"
        default_manager_name = "objects"

    @property
    def event_type(self):
        return self.event.event_type

    @property
    def related_subjects(self):
        return self.event.related_subjects

    def clean(self):
        super().clean()
        self.comment = clean_user_text(self.comment, "EventFile.comment")

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result


class EventRelationship(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = TenantForeignKey("EventRelationshipType", on_delete=models.PROTECT)
    from_event = TenantForeignKey(
        "Event", related_name="out_relationships", related_query_name="out_relationship", on_delete=models.CASCADE
    )
    to_event = TenantForeignKey(
        "Event", related_name="in_relationships", related_query_name="in_relationship", on_delete=models.CASCADE
    )
    ordernum = models.SmallIntegerField(blank=True, null=True)

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventRelationshipManager()
    tenant_id = "das_tenant_id"
    name = "Event Relationship"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "type", "from_event", "to_event"],
                name="%(app_label)s_%(class)s_tenant_type_event_unique",
            ),
        ]
        ordering = [
            "type",
            "ordernum",
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"
        permissions = [
            ("delete_event_relationship", "Can delete event relationships"),
        ]

    def __str__(self):
        return "<%s> : %s : <%s>" % (str(self.from_event), self.type.value, self.to_event)

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.from_event.dependent_table_updated()
        return result

    def clean(self):
        super().clean()

        if self.from_event == self.to_event:
            raise ValidationError(
                {"to_event": ValidationError(_("An event may not have a relationship with itself."), code="invalid")}
            )

    def delete(self, using=None, keep_parents=False):
        myid = self.id
        result = super().delete(using, keep_parents)
        self.from_event.dependent_table_updated()
        self.id = myid
        relation_deleted.send(sender=Event, relation=self, instance=self.from_event, related_query_name="relationship")

        return result


class Event(TenantModelMixin, SerialNumberModelMixin, RevisionMixin, TimestampedModel):
    """
    An Event is something that happened. Maybe an incident, or an analyzer result, or a phone call from an informant.
    """

    PC_SYSTEM = "system"
    PC_SENSOR = "sensor"
    PC_ANALYZER = "analyzer"
    PC_COMMUNITY = "community"
    PC_STAFF = "staff"

    PROVENANCE_CHOICES = (
        (PC_STAFF, "Staff"),
        (PC_SYSTEM, "System Process"),
        (PC_SENSOR, "Sensor"),
        (PC_ANALYZER, "Analyzer"),
        (PC_COMMUNITY, "Community"),
    )

    SC_NEW = SC_NEW
    SC_ACTIVE = SC_ACTIVE
    SC_RESOLVED = SC_RESOLVED

    STATE_CHOICES = STATE_CHOICES

    PRI_URGENT = PRI_URGENT
    PRI_IMPORTANT = PRI_IMPORTANT
    PRI_REFERENCE = PRI_REFERENCE
    PRI_NONE = PRI_NONE

    PRIORITY_CHOICES = PRIORITY_CHOICES

    PRIORITY_LABELS_MAP = dict((x, y) for (x, y) in PRIORITY_CHOICES)

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        # Django at the end of each migration in post_migrate signal ensures that these permissions
        # have been created for all models. This is a problem for our special case of Tenant Permissions
        # in that after each migration, the permissions here were being re-generated and assigned to the global
        # permission list. That's not the effect we want, so they have been removed from here.
        # Any permissions for events are created at the tenant level now and associated with the tenant.
        permissions = ()
        indexes = [
            models.Index(fields=["das_tenant", "created_at"]),
            models.Index(fields=["das_tenant", "updated_at"]),
            models.Index(fields=["das_tenant", "event_time"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "serial_number"], name="%(app_label)s_%(class)s_tenant_serial_number_unique"
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    serial_number = models.BigIntegerField(blank=True, unique=False, null=True, verbose_name="Serial Number")

    message = models.TextField(blank=True)
    comment = models.TextField(blank=True, null=True, verbose_name="Additional message text")

    title = models.TextField(blank=True, null=True, verbose_name="Event Title.")

    created_by_user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="events",
        related_query_name="event",
    )

    event_time = models.DateTimeField(default=django.utils.timezone.now)
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="End Time")
    provenance = models.CharField(max_length=40, choices=PROVENANCE_CHOICES, blank=True)

    event_type = TenantForeignKey(EventType, on_delete=models.PROTECT, blank=True, null=True)

    state = models.CharField(max_length=40, choices=STATE_CHOICES, default=SC_NEW, db_index=True)

    location = models.PointField(srid=4326, null=True, blank=True)

    priority = models.PositiveSmallIntegerField(default=PRI_NONE, choices=PRIORITY_CHOICES)
    attributes = models.JSONField(default=dict, blank=True)

    related_subjects = models.ManyToManyField(Subject, through="EventRelatedSubject")

    revision = Revision()

    _usermodel = settings.AUTH_USER_MODEL.lower().split(".")

    reported_by_limits = (
        models.Q(app_label="observations", model="subject")
        | models.Q(app_label="observations", model="source")
        | models.Q(app_label="activity", model="community")
        | models.Q(app_label=_usermodel[0], model=_usermodel[1])
    )

    reported_by_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, limit_choices_to=reported_by_limits, null=True, blank=True
    )

    reported_by_id = models.UUIDField(null=True, blank=True, default=None)

    reported_by = GenericForeignKey("reported_by_content_type", "reported_by_id")

    sort_at = models.DateTimeField(blank=True)
    patrol_segments = models.ManyToManyField(
        to="PatrolSegment", through="EventRelatedSegments", related_name="events", related_query_name="event"
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventManager()
    tenant_id = "das_tenant_id"

    revision_ignore_fields = "sort_at"
    revision_follow_relations = ("activity.EventPhoto",)

    @property
    def display_title(self):
        if self.title:
            return self.title

        return self.event_type.display

    @property
    def priority_label(self):
        return self.get_priority_display()

    @property
    def coordinates(self):
        return self.location

    @property
    def time(self):
        return self.event_time

    @property
    def icon_id(self):
        return self.event_type.icon_id

    @staticmethod
    def image_basename(event_type, priority, state):
        CONVERSION = {0: "gray", 100: "med_green", 200: "amber", 300: "red"}
        color = CONVERSION.get(priority, "black")
        if state == Event.SC_RESOLVED:
            color = "lt_gray"
        if not event_type:
            event_type = "other"
        return "{0}-{1}".format(event_type, color)

    @staticmethod
    def generate_image_keys(event_type_value, priority, state):
        # Generate list from most to least preferable icon.
        yield Event.image_basename(event_type_value, priority, state)

        report_suffix = "_rep"
        if event_type_value.endswith(report_suffix):
            no_suffix = event_type_value[: -1 * len(report_suffix)]
            yield Event.image_basename(no_suffix, priority, state)
            yield "{0}-{1}".format(no_suffix, "black")
        yield "{0}-{1}".format(event_type_value, "black")
        yield "{0}".format(event_type_value)
        yield Event.image_basename("generic", priority, state)
        yield "generic-black"

    @staticmethod
    def marker_icon(event_type_value, priority, state, default="/static/generic-black.svg"):
        image_url = static_image_finder.get_marker_icon(Event.generate_image_keys(event_type_value, priority, state))
        return image_url or default

    @property
    def image_url(self):
        return Event.marker_icon(self.event_type.icon_id, self.priority, self.state)

    def dependent_table_updated(self):
        # if difference is less than 1, probably means the event and other object were created together
        if abs((self.created_at - timezone.now()).total_seconds()) > 1:
            self.updated_at = timezone.now()
            self.state = "active" if self.state == "new" else self.state
            self.sort_at = self.updated_at
            self.save()

    def update_parent_events(self, **kwargs):
        # This updates all events having a 'contains' relationship directed at this event. (Ex. parent collections).
        # Event.objects.filter(out_relationship__to_event=self, out_relationship__type__value='contains') \
        #     .update(**kwargs)
        """
        This finds all the events having an indegree relation to this event, and updates them.

        The value 'contains' is a magic value that represents a relationship between a collection-event and another event.
        :param kwargs: Unused
        :return: None
        """

        parents = Event.objects.filter(out_relationship__to_event=self, out_relationship__type__value="contains")
        for parent in parents:
            parent.updated_at = self.updated_at
            parent.sort_at = self.sort_at
            parent.save(notify_parent_events=False)

    def save(self, *args, notify_parent_events=True, **kwargs):
        """

        :param args:
        :param notify_parent_events: whether to update 'parent' events (those that are collections and contain this event.)
        :param kwargs:
        :return:
        """
        self.full_clean(exclude=["id"])
        update_fields = kwargs.get("update_fields", [])
        save_fields = set()

        try:
            prev_state = self.revision_original.get("state", None)
        except AttributeError:
            prev_state = None

        # If I'm adding a record and it's sort_at has already been set.
        if self._state.adding and self.sort_at is not None:
            pass
        elif (
            len(update_fields) == 1
            and "state" in update_fields
            and self.state == self.SC_ACTIVE
            and prev_state == self.SC_NEW
        ):
            pass
        else:
            self.sort_at = timezone.now()
            save_fields.add("sort_at")

        # move the state to Active if we are stuck on New.
        if (
            not self._state.adding
            and prev_state == self.SC_NEW
            and self.state == self.SC_NEW
            and "state" not in save_fields
        ):
            self.state = self.SC_ACTIVE
            save_fields.add("state")

        save_fields.add("updated_at")
        if update_fields:
            update_fields = set(update_fields)
            update_fields.update(save_fields)
            kwargs["update_fields"] = list(update_fields)

        result = super().save(*args, **kwargs)

        if notify_parent_events:
            self.update_parent_events(updated_at=self.updated_at, sort_at=self.sort_at)

        return result

    def clean(self):
        super().clean()
        User = get_user_model()

        """validate reported_by based on provenance"""
        if self.provenance == self.PC_STAFF:
            if self.reported_by and not isinstance(self.reported_by, (User, Subject)):
                raise ValidationError(
                    {"reported_by": ValidationError(_("Invalid value for reported_by"), code="invalid")}
                )
        elif self.provenance == self.PC_COMMUNITY:
            if self.reported_by and not isinstance(self.reported_by, (Community,)):
                raise ValidationError(
                    {
                        "reported_by": ValidationError(
                            _("Invalid value for {0} reported_by".format(self.PC_COMMUNITY)), code="invalid"
                        )
                    }
                )
        elif self.provenance and self.reported_by:
            raise ValidationError(
                {
                    "reported_by": ValidationError(
                        _("Invalid value for provenance {0} and reported_by fields".format(self.provenance)),
                        code="invalid",
                    )
                }
            )

        self.message = clean_user_text(self.message, "Event.message")
        self.title = clean_user_text(self.title, "Event.title")

    def get_display_value(self, field_name, value):
        field = self._meta.get_field(field_name)
        if hasattr(self, "get_{0}_display".format(field_name)):
            return force_str(dict(field.flatchoices).get(value, value), strings_only=True)
        if field_name == "event_type":
            try:
                return force_str(EventType.objects.get(value=value).display, strings_only=True)
            except EventType.DoesNotExist:
                pass
        return value

    def __str__(self):
        return f"{self.serial_number}: ({self.title}, {self.event_type})"


class EventRelatedSegments(TenantModelMixin, UUIDModel):
    event = TenantForeignKey(Event, on_delete=models.CASCADE, null=False)
    patrol_segment = TenantForeignKey(to="PatrolSegment", on_delete=models.CASCADE, null=False)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        permissions = [
            ("delete_event_related_segments", "Can remove an event from a patrol segment"),
        ]


class EventRelatedSubject(TenantModelMixin, UUIDModel, models.Model):
    event = TenantForeignKey(Event, on_delete=models.CASCADE)
    subject = TenantForeignKey(Subject, on_delete=models.PROTECT)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    def __str__(self):
        return " <is related to> ".join((str(self.event), str(self.subject)))

    name = "Event Related Subject"
    verbose_name = "Indicates a Subject that is involved in an Event"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "event", "subject"], name="%(app_label)s_%(class)s_tenant_event_subject_unique"
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"


class EventAttachmentManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def create_attachment(self, **kwargs):
        return self.create(**kwargs)


class EventAttachment(TenantModelMixin, RevisionMixin, models.Model):
    # An event should allow attaching one or more other model objects. This model accommodates
    # attaching an object for an arbitrary model as long as its id is of type
    # UUID.

    TARGET = "target"
    ANALYZER_RESULT = "analyzer-result"
    EVENT_ATTACHMENT_REASONS = ((TARGET, "Target"), (ANALYZER_RESULT, "Analyzer Result"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # Foreign Key to event for this attachment.
    event = TenantForeignKey(
        Event, on_delete=models.CASCADE, related_name="attachments", related_query_name="attachment"
    )
    # Generic foreign key relation to any model within 'limits'. The technical constraint is the related model must
    # have id of type UUID.
    limits = (
        models.Q(app_label="observations", model="subject")
        | models.Q(app_label="observations", model="source")
        | models.Q(app_label="analyzers", model="subjectanalyzerresult")
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    target_id = models.UUIDField()
    target = GenericForeignKey("content_type", "target_id")
    reason = models.CharField(max_length=20, choices=EVENT_ATTACHMENT_REASONS, default="target")
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventAttachmentManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Event Attachment")
        verbose_name_plural = _("Event Attachments")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def __str__(self):
        # TODO: Devise a better way to represent EventAttachment.
        return "{0}:{1}".format(self.target.__str__(), self.reason)


class EventNoteManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def create_note(self, **kwargs):
        return self.create(**kwargs)


class EventNote(TenantModelMixin, RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    text = models.TextField()
    created_by_user = TenantForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    event = TenantForeignKey(Event, on_delete=models.CASCADE, related_name="notes", related_query_name="note")
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventNoteManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Event Note")
        verbose_name_plural = _("Event Notes")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def clean(self):
        super().clean()
        self.text = clean_user_text(self.text, "EventNote.text")

    def __str__(self):
        return "{0}".format(self.text[50:])


class EventDetailsManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def create_event_details(self, **kwargs):
        return self.create(**kwargs)

    def create(self, update_parent_event=True, **kwargs):
        obj = self.model(**kwargs)
        self._for_write = True
        obj.save(force_insert=True, using=self.db, update_parent_event=update_parent_event)
        return obj


class EventDetails(TenantModelMixin, RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event = TenantForeignKey(
        Event, on_delete=models.CASCADE, related_name="event_details", related_query_name="event_details"
    )
    data = models.JSONField()

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    revision = Revision()
    objects = EventDetailsManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, update_parent_event=True, **kwargs):
        result = super().save(*args, **kwargs)
        if update_parent_event:
            self.event.dependent_table_updated()
        return result


def upload_to(instance, filename):
    """
    This is a hook for providing a path to an EventPhoto.image.
    :param instance: EventPhoto instance
    :param filename: default filename.
    :return: relative path for storing uploaded image
    """
    name, extension = filename.rsplit(".", 1) if "." in filename else (filename, "")
    d = datetime.datetime.now().replace(tzinfo=pytz.UTC)
    tenant = get_tenant_settings()
    file_path = f"{tenant.slug_name}/eventphotos/{d.year}/{d.month}/{d.day}/{instance.id}/{name}.{extension}"

    return file_path


class EventPhoto(TenantModelMixin, RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_by_user = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="event_photos",
        related_query_name="event_photo",
    )
    image = VersatileImageField(upload_to=upload_to, null=True, max_length=512)
    filename = models.TextField(verbose_name="Name of uploaded image file.", default="noname")
    event = TenantForeignKey(Event, on_delete=models.CASCADE, related_name="photos", related_query_name="photo")
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result

    def clean(self):
        self.filename = self.image.name
        super().clean()

    def delete(self, using=None, keep_parents=False):
        myid = self.id
        result = super().delete(using, keep_parents)
        self.event.dependent_table_updated()
        self.id = myid
        relation_deleted.send(sender=Event, relation=self, instance=self.event, related_query_name="photo")

        return result


class EventClassFactor(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    eventclass = TenantForeignKey(EventClass, on_delete=models.CASCADE)
    eventfactor = TenantForeignKey(EventFactor, on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=Event.PRI_REFERENCE, choices=Event.PRIORITY_CHOICES)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "eventclass", "eventfactor"],
                name="%(app_label)s_%(class)s_tenant_class_factor_unique",
            ),
        ]

    @property
    def value(self):
        return "{0}_{1}".format(self.eventclass.value, self.eventfactor.value)

    def __str__(self):
        return self.value


class EventFilter(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    ordernum = models.SmallIntegerField(verbose_name="Sort order number", null=False, default=0)
    is_hidden = models.BooleanField(verbose_name="Hide this filter", default=True)
    filter_name = models.CharField(verbose_name="Display name that is meaningful to a user", null=False, max_length=100)
    filter_spec = models.JSONField(verbose_name="Filter specification", default=dict)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class EventProvider(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    display = models.CharField(
        max_length=100,
        verbose_name="Description",
        help_text="Friendly description of the Event Provider.",
        blank=True,
        default="",
    )
    is_active = models.BooleanField(default=True, verbose_name="Whether this Event Provider is active.")
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventproviders",
        related_query_name="eventprovider",
    )
    additional = models.JSONField(default=dict, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        verbose_name = _("Event Provider")
        verbose_name_plural = _("Event Providers")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.display


class EventSource(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    external_event_type = models.SlugField(
        max_length=100,
        verbose_name="External Event Type",
        help_text="External event-type identifier.",
    )
    display = models.CharField(
        max_length=100,
        verbose_name="Description",
        help_text="Friendly description of the event source.",
        blank=True,
        default="",
    )
    event_type = TenantForeignKey(EventType, on_delete=models.PROTECT, blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="Whether this EventSource may accept new events.")
    eventprovider = TenantForeignKey(
        EventProvider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventsources",
        related_query_name="eventsource",
    )
    additional = models.JSONField(default=dict, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    @property
    def is_ready(self):
        return self.is_active and self.event_type is not None

    class Meta:
        verbose_name = _("Event Source")
        verbose_name_plural = _("Event Sources")
        permissions = (("create_event_for_eventsource", "Permission to add an event for an event source"),)
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "eventprovider", "external_event_type"],
                name="%(app_label)s_%(class)s_tenant_provider_unique",
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        epname = self.eventprovider.display if self.eventprovider else "unspecified-provider"
        return f"{epname}:{self.external_event_type}"


class EventsourceEventManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def add_relation(self, event, eventsource, external_event_id):
        correlation = EventsourceEvent.objects.get_or_create(
            eventsource=eventsource,
            external_event_id=external_event_id,
            event=event,
        )
        return correlation

    def get_relation(self, eventsource, external_event_id):
        try:
            correlation = EventsourceEvent.objects.get(eventsource=eventsource, external_event_id=external_event_id)
            return correlation
        except EventsourceEvent.DoesNotExist:
            pass

    def remove_relation(self, eventsource, external_event_id):
        result = EventsourceEvent.objects.filter(eventsource=eventsource, external_event_id=external_event_id).delete()

        return result


class EventsourceEvent(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event = TenantForeignKey(
        "Event",
        related_name="eventsource_event_refs",
        related_query_name="eventsource_event_ref",
        on_delete=models.CASCADE,
    )
    eventsource = TenantForeignKey(
        "EventSource",
        related_name="eventsource_event_refs",
        related_query_name="eventsource_event_ref",
        on_delete=models.CASCADE,
    )
    external_event_id = models.CharField(max_length=100, null=False)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = EventsourceEventManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "eventsource", "external_event_id"],
                name="%(app_label)s_%(class)s_tenant_source_unique",
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"


NOTIFICATION_METHOD_EMAIL = "email"
NOTIFICATION_METHOD_SMS = "sms"
NOTIFICATION_METHOD_WHATSAPP = "whatsapp"

NOTIFICATION_METHOD_CHOICES = (
    (NOTIFICATION_METHOD_EMAIL, _("Email")),
    (NOTIFICATION_METHOD_SMS, _("SMS")),
    (NOTIFICATION_METHOD_WHATSAPP, _("WhatsApp")),
)


class NotificationMethod(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_methods",
        related_query_name="notification_method",
    )
    title = models.CharField(max_length=100, blank=True)
    method = models.CharField(default="email", max_length=20, choices=NOTIFICATION_METHOD_CHOICES)
    value = models.CharField(default="", max_length=100, help_text=_("A phone number or email address."))
    is_active = models.BooleanField(default=True, help_text=_("Whether messages should be sent to this method."))
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Notification Method")
        verbose_name_plural = _("Notification Methods")
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return f"{self.owner.username}, {self.method}, {self.value}"

    @property
    def phone_number(self):
        """Returns the formatted phone number if the method is SMS or WhatsApp, otherwise returns None.

        This property will attempt to parse and format the value field as a phone number,
        but won't raise validation errors if the number is invalid.
        """
        if self.method not in [NOTIFICATION_METHOD_SMS, NOTIFICATION_METHOD_WHATSAPP]:
            return None

        try:
            value = self.plusify_value()
            phone_number = phonenumbers.parse(value)
            if phonenumbers.is_valid_number(phone_number):
                return phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return None

    def plusify_value(self):
        """
        If the number doesn't start with +, add a +.
        Also strip leading and trailing whitespace.
        """

        value = self.value.strip()
        if not value.startswith("+"):
            value = "+" + value
        return value

    def clean(self):
        super().clean()

        if self.method in [NOTIFICATION_METHOD_SMS, NOTIFICATION_METHOD_WHATSAPP]:
            try:
                value = self.plusify_value()

                phone_number = phonenumbers.parse(value)

                if not phonenumbers.is_valid_number(phone_number):
                    raise ValidationError({"value": _("Invalid phone number format.")})

                # Format the number in E.164 format (e.g., +14155552671)
                self.value = phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException as pex:
                raise ValidationError({"value": _(f"Invalid phone number format: {pex}")})


class AlertRuleNotificationMethod(TenantThroughModel):
    alertrule = TenantForeignKey("activity.AlertRule", on_delete=models.CASCADE)
    notificationmethod = TenantForeignKey("activity.NotificationMethod", on_delete=models.CASCADE)


class AlertRuleEventType(TenantThroughModel):
    alertrule = TenantForeignKey("activity.AlertRule", on_delete=models.CASCADE)
    eventtype = TenantForeignKey("activity.EventType", on_delete=models.CASCADE)


class AlertRule(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        related_name="alert_rules",
        related_query_name="alert_rule",
    )
    title = models.CharField(max_length=100, blank=True, help_text=_("A user friendly name for this alert."))
    override_message = models.TextField(
        blank=True,
        null=True,
        help_text=_("If set, this message will be sent instead of the default alert message."),
    )
    ordernum = models.SmallIntegerField(blank=True, null=True, default=0)
    conditions = models.JSONField(default=dict, blank=True)
    schedule = models.JSONField(default=dict, blank=True)
    notification_methods = models.ManyToManyField(
        NotificationMethod,
        related_name="alert_rules",
        related_query_name="alert_rule",
        through="activity.AlertRuleNotificationMethod",
        through_fields=("alertrule", "notificationmethod"),
    )
    event_types = models.ManyToManyField(
        EventType,
        related_name="alert_rules",
        through="activity.AlertRuleEventType",
        through_fields=("alertrule", "eventtype"),
        related_query_name="alert_rule",
    )
    is_active = models.BooleanField(
        default=True,
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Alert Rule")
        verbose_name_plural = _("Alert Rules")
        base_manager_name = "objects"
        default_manager_name = "objects"

    @property
    def is_conditional(self):
        return bool(self.conditions)

    @property
    def display_title(self):
        if self.title:
            return self.title

        n = self.event_types.count()
        if n > 1:
            return f"Alert ({n} report types)"

        return f"{self.event_types.first().display} Reports"


class EventNotification(TenantModelMixin, UUIDModel, TimestampedModel):
    method = models.CharField(default="email", max_length=20, choices=NOTIFICATION_METHOD_CHOICES)
    value = models.CharField(default="", max_length=100, help_text=_("A phone number or email address."))
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_notifications",
        related_query_name="event_notification",
    )
    event = TenantForeignKey(Event, null=True, on_delete=models.SET_NULL)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Event Notification")
        verbose_name_plural = _("Event Notifications")
        indexes = [models.Index(fields=["das_tenant", "event"])]
        base_manager_name = "objects"
        default_manager_name = "objects"


class TSVectorModel(TenantModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event = TenantOneToOneField(Event, on_delete=models.CASCADE)
    tsvector_event = SearchVectorField(null=True)
    tsvector_event_note = SearchVectorField(null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "event"],
                name="%(app_label)s_%(class)s_unique",
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"


PC_OPEN = "open"
PC_DONE = "done"
PC_CANCELLED = "cancelled"

PATROL_STATE_CHOICES = (
    (PC_OPEN, "Open"),
    (PC_DONE, "Done"),
    (PC_CANCELLED, "Cancelled"),
)

PATROL_STATE_ALTERNATE_SPELLINGS = {
    "canceled": PC_CANCELLED,
}

PC_SYSTEM = "system"
PC_SENSOR = "sensor"
PC_ANALYZER = "analyzer"
PC_COMMUNITY = "community"
PC_STAFF = "staff"

PROVENANCE_CHOICES = (
    (PC_STAFF, "Staff"),
    (PC_SYSTEM, "System Process"),
    (PC_SENSOR, "Sensor"),
    (PC_ANALYZER, "Analyzer"),
    (PC_COMMUNITY, "Community"),
)


class PersonManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_queryset(self):
        return super(PersonManager, self).get_queryset().filter(subject_subtype__subject_type__value="person")


class Person(Subject):
    objects = PersonManager()

    class Meta:
        proxy = True
        verbose_name = _("Person")
        verbose_name_plural = _("People")


class MembershipType(TenantModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=100)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "value"], name="%(class)s_val_idx")]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.value


class Team(TenantModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    display = models.CharField(max_length=255, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class TeamMembership(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = TenantForeignKey("MembershipType", on_delete=models.PROTECT)
    team = TenantForeignKey("Team", related_name="members", related_query_name="member", on_delete=models.CASCADE)
    person = TenantForeignKey(
        "Person", related_name="team_memberships", related_query_name="team_membership", on_delete=models.CASCADE
    )
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"
    name = "Team Membership"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "type", "team", "person"], name="%(app_label)s_%(class)s_tenant_type_team_unique"
            ),
        ]
        ordering = [
            "type",
            "ordernum",
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"


class StateFilters(Enum):
    scheduled = "scheduled"
    active = "active"
    overdue = "overdue"
    done = PC_DONE
    cancelled = PC_CANCELLED


class PatrolFilteringQuerySet(models.QuerySet, FilterFieldMixin):
    def by_patrol_filter(self, filter):
        queryset = self._annotate_queryset_with_serial_number_string()
        if filter.get("date_range"):
            patrols_overlap_daterange = filter.get("patrols_overlap_daterange", True)
            queryset = queryset.by_date_range(filter.get("date_range"), patrols_overlap_daterange)
        if filter.get("text"):
            text = filter.get("text")
            if text:
                subjects_id = self._get_match_subjects_id(text)
                users_id = self._get_match_user_id(text)
                text = re.escape(text)
                queryset = queryset.filter(
                    Q(serial_number_string=text)
                    | Q(title__iregex=self._get_regex_istartswith(text))
                    | Q(patrol_segment__patrol_type__display__iregex=self._get_regex_istartswith(text))
                    | Q(note__text__iregex=self._get_regex_istartswith(text))
                    | Q(
                        patrol_segment__leader_id__in=subjects_id,
                        patrol_segment__leader_content_type__model="subject",
                    )
                    | Q(
                        patrol_segment__leader_id__in=users_id,
                        patrol_segment__leader_content_type__model="user",
                    )
                )

        if filter.get("patrol_type"):
            queryset = queryset.filter(Q(patrol_segment__patrol_type__id__in=filter["patrol_type"]))

        if filter.get("tracked_by"):
            queryset = queryset.filter(Q(patrol_segment__leader_id__in=filter["tracked_by"]))

        return queryset.distinct()

    def by_date_range(self, filter_param, patrols_overlap_daterange):
        queryset = self
        lower, upper = parse_date_range(filter_param)

        lower = lower or pytz.utc.localize(datetime.datetime.min)
        upper = upper or pytz.utc.localize(datetime.datetime.max)

        if patrols_overlap_daterange:
            # Patrols whose start to end date range overlaps with date range
            end_filter = Q(patrol_segment__time_range__endswith__gte=lower) | Q(
                patrol_segment__time_range__endswith__isnull=True
            )
            start_filter = Q(patrol_segment__time_range__startswith__lte=upper) | Q(
                patrol_segment__scheduled_start__lte=upper
            )
            q1 = queryset.filter(start_filter, end_filter).exclude(state=PC_CANCELLED)

            # Get patrols cancelled within given range
            q2 = queryset.annotate(
                cancel_rev_exists=Exists(
                    Patrol.revision.model.objects.filter(
                        data__state=PC_CANCELLED,
                        object_id=OuterRef("id"),
                        data__updated_at__range=(lower.isoformat(), upper.isoformat()),
                    )
                )
            ).filter(cancel_rev_exists=True)

            q3 = queryset.filter(patrol_segment__time_range__startswith__lte=upper, state=PC_OPEN)
            queryset = (q1 | q2 | q3).distinct()
        else:
            # Patrols starting within date range
            upper = (
                (upper - datetime.timedelta(minutes=1)).replace(second=59, microsecond=999999)
                if upper.time() == datetime.time(0, 0)
                else upper
            )
            start_filter = Q(patrol_segment__time_range__startswith__range=(lower, upper)) | Q(
                patrol_segment__scheduled_start__range=(lower, upper)
            )

            queryset = queryset.filter(start_filter).exclude(state=PC_CANCELLED)

        return queryset

    def exclude_patrols_without_segments(self):
        return self.exclude(patrol_segment__isnull=True)

    def by_patrol_type(self, patrol_type):
        return self.filter_field("patrol_segment__patrol_type__value", patrol_type)

    def by_state(self, states):
        now = datetime.datetime.now(tz=pytz.utc)
        q1 = q2 = q3 = q4 = q5 = self.none()

        for state in states:
            if state == StateFilters.scheduled.value:
                st_filter = Q(patrol_segment__time_range__startswith__gt=now) | Q(
                    patrol_segment__scheduled_start__gt=now
                )
                q1 = self.filter(st_filter, state=PC_OPEN)

            if state == StateFilters.active.value:
                q2 = self.filter(Q(patrol_segment__time_range__startswith__lte=now), state=PC_OPEN)

            if state == PC_DONE:
                q3 = self.filter(state=PC_DONE)

            if state == StateFilters.overdue.value:
                supposed_start = now - datetime.timedelta(minutes=30)
                st_filter = Q(patrol_segment__time_range__startswith__isnull=True) & Q(
                    patrol_segment__scheduled_start__lte=supposed_start
                )
                q4 = self.filter(st_filter, state=PC_OPEN)

            if state == PC_CANCELLED:
                q5 = self.filter(state=PC_CANCELLED)

        return (q1 | q2 | q3 | q4 | q5).distinct()

    def by_subject(self, subject):
        return self.filter_field("patrol_segment__leader_id", subject)

    def sort_patrols(self):
        set_time = datetime.datetime.now(tz=pytz.utc) - datetime.timedelta(minutes=30)
        subject = Subject.objects.filter(id=OuterRef("patrol_segment__leader_id"))

        overdue_q = (
            Q(patrol_segment__scheduled_start=F("patrol_segment__scheduled_start"), state=PC_OPEN)
            & Q(patrol_segment__time_range__startswith__isnull=True)
            & Q(patrol_segment__scheduled_start__lt=set_time)
        )

        readyto_q = (
            Q(patrol_segment__scheduled_start=F("patrol_segment__scheduled_start"), state=PC_OPEN)
            & Q(patrol_segment__time_range__startswith__isnull=True)
            & Q(patrol_segment__scheduled_start__gte=set_time)
        )

        return self.annotate(
            start_overdue=Case(
                When(overdue_q & Q(title=F("title")), then=F("title")),
                When(
                    overdue_q & Q(patrol_segment__leader_id=F("patrol_segment__leader_id")),
                    then=Subquery(subject.values("name")),
                ),
                When(
                    overdue_q & Q(patrol_segment__patrol_type__display=F("patrol_segment__patrol_type__display")),
                    then=F("patrol_segment__patrol_type__display"),
                ),
                default=None,
            ),
            readyto_start=Case(
                When(readyto_q & Q(title=F("title")), then=F("title")),
                When(
                    readyto_q & Q(patrol_segment__leader_id=F("patrol_segment__leader_id")),
                    then=Subquery(subject.values("name")),
                ),
                When(
                    readyto_q & Q(patrol_segment__patrol_type__display=F("patrol_segment__patrol_type__display")),
                    then=F("patrol_segment__patrol_type__display"),
                ),
                default=None,
            ),
            sort_title=Case(
                When(Q(title=F("title")), then=F("title")),
                When(
                    Q(patrol_segment__leader_id=F("patrol_segment__leader_id")), then=Subquery(subject.values("name"))
                ),
                default=F("patrol_segment__patrol_type__display"),
            ),
        ).order_by(
            Case(
                When(state=PC_OPEN, then=Value(1)),
                When(state=PC_DONE, then=Value(2)),
                When(state=PC_CANCELLED, then=Value(3)),
                default=Value(4),
            ),
            Lower("start_overdue"),
            Lower("readyto_start"),
            Lower("sort_title"),
        )

    def _get_regex_istartswith(self, text):
        return r"(^|\s)%s" % text

    def _get_match_subjects_id(self, subject_name):
        text = re.escape(subject_name)
        return Subject.objects.filter(name__iregex=self._get_regex_istartswith(text)).values_list("id", flat=True)

    def _get_match_user_id(self, user):
        User = get_user_model()
        text = re.escape(user)
        return User.objects.filter(
            Q(username__iregex=self._get_regex_istartswith(text))
            | Q(first_name__iregex=self._get_regex_istartswith(text))
            | Q(last_name__iregex=self._get_regex_istartswith(text))
        ).values_list("id", flat=True)

    def _annotate_queryset_with_serial_number_string(self):
        return self.annotate(serial_number_string=Cast("serial_number", CharField()))


class PatrolManager(TenantManagerMixin, models.Manager.from_queryset(PatrolFilteringQuerySet)):
    use_in_migrations = True


class Patrol(TenantModelMixin, SerialNumberModelMixin, TimestampedModel, RevisionMixin):
    PRIORITY_CHOICES = PRIORITY_CHOICES
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    serial_number = models.BigIntegerField(verbose_name="Serial Number", unique=False, blank=True, null=True)
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=PRI_NONE)
    state = models.CharField(choices=PATROL_STATE_CHOICES, default=PC_OPEN, max_length=25)
    title = models.CharField(max_length=255, blank=True, null=True)
    objective = models.TextField(blank=True, null=True)
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = PatrolManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "serial_number"], name="%(app_label)s_%(class)s_tenant_serial_number_unique"
            ),
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.title or f"Patrol #{self.serial_number}"

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self._update_patrol_state()
        super().save(force_insert, force_update, using, update_fields)

    def _update_patrol_state(self):
        now = datetime.datetime.now(tz=pytz.utc)
        for segment in self.patrol_segments.all():
            if (
                segment.time_range
                and segment.time_range.lower
                and segment.time_range.upper
                and segment.time_range.upper < now
            ):
                logger.debug(
                    f"Updating status patrol due to segment.time_ranger.upper: "
                    f"{segment.time_range.upper} is lower than {now}"
                )
                self.state = PC_DONE
            elif segment.time_range and all([segment.time_range.upper is None, self.state == PC_DONE]):
                self.state = PC_OPEN


class PatrolNote(TenantModelMixin, RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    text = models.TextField()
    created_by_user = TenantForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    patrol = TenantForeignKey(Patrol, on_delete=models.CASCADE, related_name="notes", related_query_name="note")
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class PatrolFile(TenantModelMixin, TimestampedModel, RevisionMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    patrol = TenantForeignKey("Patrol", related_name="files", related_query_name="file", on_delete=models.CASCADE)
    comment = models.TextField(blank=True, null=False, default="", verbose_name="Comment about the file.")
    relation_limits = models.Q(app_label="usercontent", model="filecontent") | models.Q(
        app_label="usercontent", model="imagefilecontent"
    )
    created_by = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patrol_files",
        related_query_name="patrol_file",
    )
    # Generic foreign key to plugin
    usercontent_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=relation_limits)
    usercontent_id = models.UUIDField()
    usercontent = GenericForeignKey("usercontent_type", "usercontent_id")
    ordernum = models.SmallIntegerField(blank=True, null=True)
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class PatrolTypeManager(EventBaseManager):
    def create_type(self, **values):
        return self.create(**values)

    def get_by_natural_key(self, value):
        return self.get(value=value)


class PatrolType(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    value = models.CharField(max_length=50)
    display = models.CharField(max_length=255)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    icon = models.CharField(max_length=100, blank=True)
    default_priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=PRI_NONE)
    is_active = models.BooleanField(default=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = PatrolTypeManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Patrol Type")
        verbose_name_plural = _("Patrol Types")
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "value"], name="%(class)s_val_idx")]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.display

    @property
    def icon_id(self):
        if not self.icon:
            if static_image_finder.get_marker_icon(PatrolType.generate_image_keys(self.value)):
                return self.value
            return DEFAULT_EVENT_PATROL_ICON_ID
        return self.icon

    @staticmethod
    def generate_image_keys(obj_icon):
        yield obj_icon

    @staticmethod
    def marker_icon(patroltype_value, default="/static/generic-black.svg"):
        image_url = static_image_finder.get_marker_icon(PatrolType.generate_image_keys(patroltype_value))
        return image_url or default

    @property
    def image_url(self):
        return PatrolType.marker_icon(self.icon_id)


class PatrolSegmentMembership(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = TenantForeignKey("MembershipType", on_delete=models.PROTECT)
    patrol_segment = TenantForeignKey(
        "PatrolSegment", related_name="members", related_query_name="member", on_delete=models.CASCADE
    )
    person = TenantForeignKey(
        "Person",
        related_name="patrolsegment_memberships",
        related_query_name="patrolsegment_membership",
        on_delete=models.CASCADE,
    )
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"
    name = "Patrol Segment Membership"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "type", "patrol_segment", "person"],
                name="%(app_label)s_%(class)s_tenant_type_unique",
            ),
        ]

        ordering = [
            "type",
            "ordernum",
        ]
        base_manager_name = "objects"
        default_manager_name = "objects"


class PatrolSegmentManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    @staticmethod
    def get_subjects(user=None) -> QuerySet:
        active_subjects = (
            Subject.objects.prefetch_related(
                Prefetch(
                    "subjectstatus_set",
                    queryset=SubjectStatus.objects.filter(delay_hours=0),
                )
            )
            .select_related("subject_subtype", "subject_subtype__subject_type")
            .all()
            .by_is_active()
        )
        subject_groups = PatrolConfiguration.objects.first().effective_subject_groups
        subjects_available = active_subjects.by_subjectgroups(subject_groups, user=user)

        return subjects_available

    @staticmethod
    def get_leader_for_provenance(provenance, user=None):
        if PC_STAFF == provenance:
            subjects = [(subject.name.lower(), subject) for subject in PatrolSegmentManager.get_subjects(user=user)]

            for sub in sorted(subjects, key=itemgetter(0)):
                yield sub[1]


class PatrolSegmentRevisionAdapter(RevisionAdapter):
    def get_serialized_data_diff(self, obj, original):
        fields = list(self.get_fieldnames())
        obj_data = self._serialize(obj, fields)

        def to_datetime(data):
            if data.get("lower"):
                data["lower"] = dparse(data["lower"])
            if data.get("upper"):
                data["upper"] = dparse(data["upper"])
            return data

        serialized_data = {}
        for fieldname in fields:
            if fieldname == "time_range":
                old_data = (
                    set(to_datetime(json.loads(original.get(fieldname))).items()) if original.get(fieldname) else set()
                )
                new_data = (
                    set(to_datetime(json.loads(obj_data.get(fieldname))).items()) if obj_data.get(fieldname) else set()
                )

                difference = new_data - old_data
                serialized_data[fieldname] = json.dumps(dict(difference), cls=DjangoJSONEncoder)

            elif original.get(fieldname, None) != obj_data.get(fieldname, None):
                serialized_data[fieldname] = obj_data.get(fieldname)
        return serialized_data


class PatrolSegmentRevision(Revision):
    revision_adapter = PatrolSegmentRevisionAdapter


class PatrolSegment(TenantModelMixin, TimestampedModel, RevisionMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    patrol = TenantForeignKey(
        Patrol, on_delete=models.CASCADE, related_name="patrol_segments", related_query_name="patrol_segment"
    )
    patrol_type = TenantForeignKey(PatrolType, on_delete=models.SET_NULL, blank=True, null=True)
    scheduled_start = models.DateTimeField(blank=True, null=True)
    scheduled_end = models.DateTimeField(blank=True, null=True)
    time_range = DateTimeRangeField(null=True, blank=True)
    start_location = models.PointField(srid=4326, blank=True, null=True)
    end_location = models.PointField(srid=4326, blank=True, null=True)
    _usermodel = settings.AUTH_USER_MODEL.lower().split(".")
    leader_limits = models.Q(app_label="observations", model="subject") | models.Q(
        app_label=_usermodel[0], model=_usermodel[1]
    )
    leader_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,  # deleting a subject should not delete the patrol segment
        limit_choices_to=leader_limits,
        null=True,
        blank=True,
    )
    leader_id = models.UUIDField(null=True, blank=True, default=None)
    leader = GenericForeignKey("leader_content_type", "leader_id")
    revision = PatrolSegmentRevision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = PatrolSegmentManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class PatrolConfiguration(TenantSingletonModel):
    # The SingletonModel requires us to create a static single instance_id
    # this instance_id is used to ensure there is only one record per tenant
    instance_id = uuid.UUID("deb99202-2373-4c6c-b05f-e71d29cb2b26")
    name = models.CharField(max_length=255)
    subject_groups = models.ManyToManyField(
        SubjectGroup, related_name="groups", blank=True, through="activity.PatrolConfigurationSubjectGroup"
    )
    objects = CommonTenantManager()

    @property
    def effective_subject_groups(self):
        effective_subject_groups = set()
        for subject_group in self.subject_groups.all():
            effective_subject_groups.add(subject_group.id)
            effective_subject_groups.update((descendant.id for descendant in subject_group.get_descendants()))

        return SubjectGroup.objects.filter(id__in=effective_subject_groups)


class PatrolConfigurationSubjectGroup(TenantModelMixin, UUIDModel):
    patrolconfiguration = TenantForeignKey(blank=True, on_delete=models.CASCADE, to="activity.patrolconfiguration")
    subjectgroup = TenantForeignKey(blank=True, on_delete=models.CASCADE, to="observations.subjectgroup")
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class EventGeometry(TenantModelMixin, RevisionMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    geometry = models.GeometryField(srid=4326, geography=True)
    event = TenantForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="geometries",
        related_query_name="geometries",
    )
    properties = models.JSONField(default=dict, blank=True)
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    @transaction.atomic
    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.event.dependent_table_updated()
        return result
