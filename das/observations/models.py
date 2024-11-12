"""
DAS DB models

after making changes to a model run migrations to record changes:
* python manage.py makemigrations --name "interesting model change name"

To re-sync your database with changes from others
* python manage.py migrate


GIS
* default geodjango spatial reference system is WGS84 (SRID 4326)
"""

import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import reduce
from operator import getitem
from typing import NamedTuple, Set

import pymet
import pytz
from bitfield import BitField
from dateutil.parser import parse as parse_date
from django_multitenant.fields import TenantForeignKey, TenantOneToOneField
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from psycopg2.extras import DateTimeTZRange

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.gis.db import models as dbmodels
from django.contrib.gis.geos import Point, Polygon
from django.contrib.postgres.fields import DateTimeRangeField, jsonb
from django.contrib.postgres.fields.hstore import KeyTransform
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import connections, transaction
from django.db.models import (
    BooleanField,
    Case,
    ExpressionWrapper,
    F,
    FilteredRelation,
    Index,
    Max,
    Q,
    Value,
    When,
)
from django.db.models.constraints import UniqueConstraint
from django.db.models.functions import Greatest
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from accounts.mixins import PermissionSetGroupMixin, create_permissionsethierarchy_mixin
from accounts.models import PermissionSet
from core.models import DASTenant, HierarchyManager, TimestampedModel, UUIDModel
from core.models.hierachy import (
    TenantHierarchyModel,
    create_tenanthierarchychildren_model,
)
from core.utils import static_image_finder
from das_server import settings
from observations.mixins import FilterMixin
from observations.utils import (
    VIEW_END_WINDOWS,
    calculate_track_range,
    ensure_timezone_aware,
    get_cyclic_subjectgroup,
    get_minimum_allowed_age,
    is_subject_stationary_subject,
)
from tracking.pubsub_registry import notify_subjectstatus_update
from utils.decorator import use_shared_resource
from utils.interfaces import SharedResourceHandler
from utils.json import zeroout_microseconds
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager, get_next_int_val
from utils.tenant.thread import get_tenant_settings

User = get_user_model()

STATIONARY_SUBJECT_VALUE = "stationary-object"

logger = logging.getLogger(__name__)
GPX_FILES_FOLDER = getattr(settings, "GPX_FILES_FOLDER", "observations/gpxfile")


SOURCE_TYPES = sorted(
    (
        ("tracking-device", "Tracking Device"),
        ("trap", "Trap"),
        ("seismic", "Seismic sensor"),
        ("firms", "FIRMS data"),
        ("gps-radio", "GPS radio"),
    ),
    key=lambda item: item[1],
)


def to_rgb(color):
    try:
        return "#{0:02X}{1:02X}{2:02X}".format(*[int(val) for val in color.split(",")])
    except:
        raise


DEFAULT_COLOR = "255,255,0"

STATUS_COLORS = {"online-gps": "green", "online": "blue", "offline": "gray", "alarm": "red", "na": "black"}


def random_rgb():
    return ",".join([str(random.randint(0, 255)) for i in range(3)])


def Condition(*args, **kwargs):
    return ExpressionWrapper(Q(*args, **kwargs), output_field=BooleanField())


class SourceGroupManager(HierarchyManager):
    use_in_migrations = True

    def get_default(self):
        defaults = dict(name="Sources")
        source_group, created = self.get_or_create(id=DEFAULT_SOURCE_GROUP_ID, defaults=defaults)
        return source_group

    def get_by_natural_key(self, name):
        return self.get(**{"name": name})


class SourceGroup(
    TenantHierarchyModel, TimestampedModel, create_permissionsethierarchy_mixin("observations.SourceGroupPermissionSet")
):
    """
    Manage Groups of sources so that we can easily set permissions on a group
    rather than each individual Source. Additionally there are requests to
    get a subset of Sources.

    A group can contain other groups as well.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_("name"), max_length=80)
    sources = models.ManyToManyField(
        "observations.Source", related_name="groups", blank=True, through="observations.SourceGroupSource"
    )

    children = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="_parents",
        through="observations.SourceGroupChildren",
    )

    objects = SourceGroupManager()

    class Meta:
        verbose_name = _("source group")
        verbose_name_plural = _("source groups")
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            ),
        ]
        indexes = [
            Index(fields=["das_tenant", "name"]),
        ]

    def __str__(self):
        return self.name

    def get_all_sources(self, user=None, active=None, include_from_subgroups=True, **kwargs):
        """Including descendant group sources"""
        sources = set(iter(self.sources.all()))

        if include_from_subgroups:
            subgroups = self.get_descendants()
            for group in subgroups:
                sources.update(iter(group.sources.all()))
        return list(sources)

    @property
    def is_visible(self):
        """should the group be displayed in a UI
            symmetry with SubjectGroup, return True
        Returns:
            [bool]: is visible
        """
        return True

    def natural_key(self):
        return (self.name,)


SourceGroupChildren = create_tenanthierarchychildren_model(SourceGroup, through_fieldname="sources")


class SourceQuerySet(models.QuerySet, FilterMixin):
    def by_active_sources(self):
        """filter sources currently connected to subjects that are active. Currently connected is defined as
        having an assigned range that contains the current time."""
        sources = self.filter(
            subjectsource__assigned_range__contains=datetime.now(tz=timezone.utc),
            subjectsource__subject__is_active=True,
        )
        return sources

    def by_disconnected_sources(self):
        """filter to those sources not currently connected to subjects."""
        sources = self.exclude(subjectsource__assigned_range__contains=datetime.now(tz=timezone.utc))
        return sources


class SourceManager(TenantManagerMixin, models.Manager.from_queryset(SourceQuerySet)):
    use_in_migrations = True

    # Helper functions for hydrating Source and Subject for the given message.
    def ensure_source(self, *args, **kwargs):
        subject_info = kwargs.get("subject")

        with transaction.atomic():
            source, source_created = self.get_source(**kwargs)
            if source_created:
                # Getting here means we've created a source.
                # We should create a Subject for it too.
                source.groups.set((SourceGroup.objects.get_default(),))

                if subject_info:
                    # Create a subject-subtype on demand if necessary.
                    subject_subtype_id = subject_info.get("subject_subtype_id")
                    if isinstance(subject_subtype_id, str):
                        default_display = subject_subtype_id[:100].title()
                        SubjectSubType.objects.get_or_create(
                            value=subject_subtype_id, defaults={"display": default_display}
                        )

                    if subject_info.get("id"):
                        try:
                            subject_model = Subject.objects.get(id=subject_info.get("id"))
                        except Subject.DoesNotExist:
                            subject_model = Subject.objects.create_subject(**subject_info)
                    else:
                        subject_model = Subject.objects.create_subject(**subject_info)
                else:
                    subject_model = Subject.objects.create_subject(**{"name": source.manufacturer_id})

                if not SubjectSource.objects.filter(source=source, subject=subject_model):
                    SubjectSource.objects.create(source=source, subject=subject_model)

            return source

    def get_source(
        self, *, provider=None, manufacturer_id=None, model_name=None, source_type=None, additional=None, **kwargs
    ):
        additional = additional or {}
        if not isinstance(provider, SourceProvider):
            provider = SourceProvider.objects.create_provider(provider_key=provider)

        searchkey = dict(manufacturer_id=manufacturer_id, provider=provider)
        defaults = {"source_type": source_type, "model_name": model_name, "additional": additional}

        return Source.objects.get_or_create(defaults=defaults, **searchkey)


class SourceProviderManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def create_provider(self, **kwargs):
        provider_key = kwargs.get("provider_key")
        if provider_key:
            try:
                provider = SourceProvider.objects.get(provider_key=provider_key)
            except SourceProvider.DoesNotExist:
                if not kwargs.get("display_name"):
                    kwargs["display_name"] = " ".join(x.capitalize() or "_" for x in provider_key.split("_"))
                provider = SourceProvider.objects.create(**kwargs)
            return provider


DEFAULT_SOURCE_PROVIDER_ID = "697f25e4-562c-4305-af86-1333e9081f4c"
DEFAULT_SOURCE_PROVIDER_KEY = "default"


def get_default_source_provider_id():
    return uuid.UUID(DEFAULT_SOURCE_PROVIDER_ID)


class SourceProvider(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    provider_key = models.CharField("Natural key for source provider", max_length=100, null="False")
    display_name = models.CharField(
        "Display name for source provider.",
        max_length=100,
        null=False,
    )
    notes = models.TextField(blank=True, null=True)
    additional = models.JSONField("additional data", default=dict, blank=True)
    transforms = models.JSONField(name="transforms", default=list, blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = SourceProviderManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "provider_key"],
                name="%(app_label)s_%(class)s_unique_provider_key_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "provider_key"])]

    def __str__(self):
        return "{} ({})".format(self.display_name, self.provider_key)


class Source(TenantModelMixin, TimestampedModel):
    """Collar, MotoTrbo, sensor, etc"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_type = models.CharField("type of data expected", max_length=100, null=True, choices=SOURCE_TYPES)

    # # Delete this after migration occurs for provider attribute.
    # provider_name = models.CharField('unique name for data provider', max_length=100, null='False', default='default')

    provider = TenantForeignKey(
        SourceProvider,
        related_name="sources",
        related_query_name="source",
        null=False,
        default=get_default_source_provider_id,
        on_delete=models.PROTECT,
    )

    manufacturer_id = models.CharField("device manufacturer id", max_length=100, null=True)
    model_name = models.CharField("device model name", max_length=201, null=True)
    additional = models.JSONField("additional data", default=dict, blank=True)
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sources",
        related_query_name="source",
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = SourceManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "provider", "manufacturer_id"],
                name="%(app_label)s_%(class)s_tenant_provider_manu_unique",
            ),
        ]

    def __str__(self):
        return f"{self.manufacturer_id} ({self.provider.provider_key})"

    def observations(self):
        queryset = Observation.objects.filter(source=self)
        return queryset

    @cached_property
    def active_subject(self):
        """Get the active subject associated with this source"""
        subject_source = (
            SubjectSource.objects.select_related("subject")
            .filter(source_id=self.pk, assigned_range__contains=datetime.now(tz=timezone.utc), subject__is_active=True)
            .order_by("-assigned_range")
            .first()
        )

        return subject_source.subject if subject_source else None


EMPTY_POINT = Point(0, 0)


class ObservationQuerySet(models.QuerySet, FilterMixin):
    def by_subject_id(self, subject_id):
        return self.filter(source__subjectsource__subject_id=subject_id)

    def by_source_id(self, source_id):
        return self.filter(source__id=source_id)

    def by_since(self, recorded_since):
        return self.filter(recorded_at__gte=recorded_since)

    def by_until(self, recorded_until):
        return self.filter(recorded_at__lte=recorded_until)

    def by_since_until(self, recorded_since, recorded_until):
        if recorded_since and recorded_until:
            return self.filter(recorded_at__range=[recorded_since, recorded_until])
        elif recorded_since:
            return self.by_since(recorded_since)
        elif recorded_until:
            return self.by_until(recorded_until)
        return self

    def by_created_after(self, timestamp):
        return self.filter(created_at__gte=timestamp)

    def by_exclusion_flags(self, filter_flag=None, include_empty_location: bool = False):
        """Works with more than one filter flag, for example 3 which is manual and automatic exclusion.

        Args:
            filter_flag (optional): the exclusion filter flag, think bits. 0 is a valid value. Defaults to None.
            include_empty_location (bool, optional): don't filter out locations that are 0,0. Defaults to False.

        Returns:
            queryset: a further filtered queryset
        """
        queryset = self
        if filter_flag is not None:
            if filter_flag > 0:
                queryset = queryset.annotate(exclusion_filter=F("exclusion_flags").bitand(filter_flag)).filter(
                    exclusion_filter__gt=0
                )
            else:
                queryset = queryset.filter(exclusion_flags=filter_flag)
            if not include_empty_location:
                queryset = queryset.exclude(location=EMPTY_POINT)
        return queryset

    def annotate_transforms(self):
        return self.annotate(source_transforms=F("source__provider__transforms"))

    def get_subjectsource_observations(
        self, subjectsource, since=None, until=None, limit=None, values=None, filter_flag=0, order_by=None
    ):
        queryset = self.filter(
            source__subjectsource=subjectsource, source__subjectsource__assigned_range__contains=F("recorded_at")
        )

        queryset = queryset.by_since_until(since, until)
        queryset = queryset.by_exclusion_flags(filter_flag)

        if order_by:
            queryset = queryset.order_by(order_by)

        if limit and limit > 0:
            queryset = queryset[:limit]

        if values:
            queryset = queryset.values(*values)

        return queryset

    def get_source_observations(
        self,
        source,
        since=None,
        until=None,
        limit=None,
        values=None,
        filter_flag=0,
        order_by=None,
        include_empty_location=True,
    ):
        queryset = self.filter(source=source)
        queryset = queryset.by_since_until(since, until)
        queryset = queryset.by_exclusion_flags(filter_flag)

        if not include_empty_location:
            queryset = queryset.exclude(location=EMPTY_POINT)

        if order_by:
            queryset = queryset.order_by(order_by)

        if limit and limit > 0:
            queryset = queryset[:limit]

        if values:
            queryset = queryset.values(*values)

        return queryset

    def get_subject_observations(
        self, subject, since=None, until=None, limit=None, values=None, filter_flag=0, order_by=None
    ):
        queryset = self.filter(
            source__subjectsource__subject=subject, source__subjectsource__assigned_range__contains=F("recorded_at")
        )

        queryset = queryset.by_since_until(since, until)

        if not isinstance(subject, Subject):
            subject = Subject.objects.get(id=subject)

        queryset = queryset.by_exclusion_flags(filter_flag, include_empty_location=subject.is_stationary_subject)

        if order_by:
            queryset = queryset.order_by(order_by)

        if limit and limit > 0:
            queryset = queryset[:limit]

        if values:
            queryset = queryset.values(*values)

        return queryset

    def get_subject_observations_values(
        self, subject, since=None, until=None, limit=None, values=("recorded_at", "location"), filter_flag=0
    ):
        return self.get_subject_observations(
            subject, since=since, until=until, limit=limit, values=values, filter_flag=filter_flag
        )


class ObservationManager(TenantManagerMixin, models.Manager.from_queryset(ObservationQuerySet)):
    use_in_migrations = True

    def set_flag(self, id_list, flags):
        """Hide the nuances of manipulating a bitmap associated with an observation."""
        Observation.objects.filter(id__in=id_list).update(exclusion_flags=F("exclusion_flags").bitor(flags))

    def unset_flag(self, id_list, flags):
        """Hide the nuances of zeroing bits in a bitmap."""
        Observation.objects.filter(id__in=id_list).update(exclusion_flags=F("exclusion_flags").bitand(~flags))

    def get_subject_source_observation_values(self, subject_source, since=None, until=None, limit=None, filter_flag=0):
        values = ("recorded_at", "location")
        queryset = Observation.objects.filter(
            source__subjectsource__in=subject_source,
            source__subjectsource__assigned_range__contains=F("recorded_at"),
            exclusion_flags=filter_flag,
        )

        if since and until:
            queryset = queryset.filter(recorded_at__range=(since, until))
        elif since:
            queryset = queryset.filter(recorded_at__gte=since)
        elif until:
            queryset = queryset.filter(recorded_at__lte=until)

        queryset = queryset.exclude(location=EMPTY_POINT)
        queryset = queryset.order_by("-recorded_at")

        if limit:
            queryset = queryset[:limit]

        return queryset.values(*values)

    def add_observation(self, observation):
        """
        Add an observation for the given source.
        :param source:
        :param observation: An object with attributes: source, latitude, longitude, recorded_at, additional
        :return: The new Observation
        """
        location = Point(x=observation.longitude, y=observation.latitude)
        additional = observation.additional or {}
        result, created = Observation.objects.get_or_create(
            source_id=observation.source.id,
            recorded_at=observation.recorded_at,
            defaults=dict(location=location, additional=additional),
        )
        return result, created

    def get_max_recorded_at(self, source):
        """Get the latest recorded timestamp for the source."""
        r = Observation.objects.filter(source=source).aggregate(Max("recorded_at"))
        return r.get("recorded_at__max")

    def get_last_source_observation(self, source, include_empty_location: bool = False, delay_hours: int = 0):
        try:
            queryset = Observation.objects.filter(source=source)

            if delay_hours:
                end_time = pytz.utc.localize(datetime.utcnow()) - timedelta(hours=delay_hours)
                queryset = queryset.filter(recorded_at__lt=end_time)

            if not include_empty_location:
                queryset = queryset.exclude(location=EMPTY_POINT)

            return queryset.latest("recorded_at")

        except Observation.DoesNotExist:
            pass


class Observation(TenantModelMixin, models.Model):
    # Constants for filter bit-map.
    DEFAULT = 0
    EXCLUDED_MANUALLY = 1
    EXCLUDED_AUTOMATICALLY = 2

    BITMAP_FILTER_CHOICES = [
        ("EXCLUDED_MANUALLY", _("EXCLUDED_MANUALLY")),
        ("EXCLUDED_AUTOMATICALLY", _("EXCLUDED_AUTOMATICALLY")),
    ]

    """observation point
    similar to archive_loc
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    location = models.PointField("point location")
    # point in time of object at lat lon.
    # Note: index is set to false, as we add a compound geospatial index
    # via a migration script
    recorded_at = models.DateTimeField("recorded at", db_index=False)
    created_at = models.DateTimeField("row created at", auto_now_add=True, db_index=True)  # date/time this row created
    source = TenantForeignKey("Source", on_delete=models.CASCADE)
    additional = models.JSONField(null=True, blank=True)
    exclusion_flags = BitField(flags=BITMAP_FILTER_CHOICES, default=0)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = ObservationManager()
    tenant_id = "das_tenant_id"

    def __str__(self):
        return "{}:{}:{:08b}".format(self.recorded_at.isoformat(), self.location, self.exclusion_flags.mask)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "source", "recorded_at"], name="%(app_label)s_%(class)s_tenant_source_at_unique"
            ),
        ]
        ordering = ["-recorded_at"]


DEFAULT_ASSIGNED_RANGE = list((pytz.utc.localize(datetime.min), pytz.utc.localize(datetime.max)))


class SubjectSourceQuerySet(models.QuerySet, FilterMixin):
    def by_two_way_messaging_enabled(self):
        return (
            self.annotate(
                two_way_messaging=jsonb.KeyTransform("two_way_messaging", "source__provider__additional"),
                source_two_way_messaging=jsonb.KeyTransform("two_way_messaging", "source__additional"),
            )
            .exclude(
                Q(two_way_messaging__isnull=True)
                | Q(two_way_messaging=False)
                | (
                    Q(two_way_messaging=True)
                    & (Q(source_two_way_messaging=False, source_two_way_messaging__isnull=False))
                )
            )
            .prefetch_related("source", "source__provider")
        )

    def by_updated_since(self, updated_since) -> models.QuerySet:
        """
        Filter queryset by updated_since datetime.
        Given a queryset of SubjectSources.

        :param updated_since:
        :return: queryset of SubjectSources.
        """
        updated_since_filter = (
            Q(subject__subjectstatus__updated_at__gte=updated_since)
            | Q(subject__subjectstatus__recorded_at__gte=updated_since)
            | Q(subject__subjectstatus__last_voice_call_start_at__gte=updated_since)
            | Q(subject__subjectstatus__radio_state_at__gte=updated_since)
        )

        queryset = self.filter(updated_since_filter).order_by("id").distinct("id")
        return queryset


class SubjectSourceManager(TenantManagerMixin, models.Manager.from_queryset(SubjectSourceQuerySet)):
    use_in_migrations = True

    def get_subject_sources(self, subject):
        sds = SubjectSource.objects.filter(subject_id=subject.id)
        return sds

    def get_subject_source(self, subject, source_id):
        sds = SubjectSource.objects.filter(subject_id=subject.id, source_id=source_id)
        return sds

    def get_subjects_sources(self, subjects=None, sources=None):
        queryset = self

        if subjects:
            queryset = queryset.filter(subject_id__in=subjects)
        if sources:
            queryset = queryset.filter(source_id__in=sources)

        return queryset

    def ensure(self, source, subject, assigned_range=None, location=None):
        """
        :param source: Source object
        :param subject: Subject object
        :param assigned_range: List datetime objects
        :param location: Dict {"latitude": 12.0, "longitude"}
        :return: SubjectSource object
        """
        assigned_range = assigned_range or DEFAULT_ASSIGNED_RANGE

        subject_source, created = SubjectSource.objects.get_or_create(
            source=source,
            subject=subject,
            assigned_range=assigned_range,
            defaults=dict(
                additional={},
            ),
            location=location,
        )

        return subject_source

    def ensure_subject_source(
        self, source, timestamp=None, subject_subtype_id=None, additional=None, subject_name=None
    ):
        # TODO: Deprecate the use of this function, in favor of the ensure().
        # And let the caller handle creating related objects if necessary.

        additional = additional or {}

        # get the most recent Subject for this Source
        subject_source = (
            SubjectSource.objects.filter(source=source, assigned_range__contains=timestamp)
            .order_by("assigned_range")
            .reverse()
            .first()
        )

        created = False

        if not subject_source:
            sub, created = Subject.objects.get_or_create(
                subject_subtype_id=subject_subtype_id,
                name=(subject_name or source.manufacturer_id),
                defaults=dict(additional=dict(region="", country="", rgb=random_rgb())),
            )

            if sub:
                subject_source, created = SubjectSource.objects.get_or_create(
                    source=source,
                    subject=sub,
                    defaults=dict(assigned_range=DEFAULT_ASSIGNED_RANGE, additional=additional),
                )

        return subject_source, created

    def get_for_source_at_time(self, source, at_time):
        subject_sources = SubjectSource.objects.filter(source=source, assigned_range__contains=at_time)
        if subject_sources:
            return subject_sources[0]


class AssignedRangeBounds(NamedTuple):
    lower: datetime
    upper: datetime


class SubjectSource(TenantModelMixin, models.Model):
    """A Subject is associated with a Source device for a specific time period
    For example a Ranger carries a specific radio between 1/1/2015 and 1/2/2015
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    assigned_range = DateTimeRangeField("time assigned to subject", default=DEFAULT_ASSIGNED_RANGE)
    source = TenantForeignKey("Source", on_delete=models.CASCADE)
    subject = TenantForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="subjectsources", related_query_name="subjectsource"
    )
    additional = models.JSONField("additional", default=dict, blank=True)
    """EXCLUDE USING gist (source_id WITH =, assigned_range WITH &&)"""
    location = models.PointField(verbose_name="Assigned location", blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = SubjectSourceManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Subject Source Assignment")
        verbose_name_plural = _("Subject Source Assignments")

    def __str__(self):
        ind = " (expired)" if datetime.now(tz=pytz.utc) not in self.assigned_range else ""
        return f"{self.subject.name} <-> {self.source.manufacturer_id}{ind}"

    @property
    def safe_assigned_range(self):
        # The app should never assign 'empty' to assigned_range, but add these guards in case
        # data enters the database through other means.
        if self.assigned_range.isempty:
            return AssignedRangeBounds(lower=pytz.utc.localize(datetime.min), upper=pytz.utc.localize(datetime.min))
        return AssignedRangeBounds(lower=self.assigned_range.lower, upper=self.assigned_range.upper)

    @safe_assigned_range.setter
    def safe_assigned_range(self, value):
        raise NotImplementedError("Please use .assigned_range directly to set its value.")

    def save(self, *args, **kwargs):
        # guard against "empty" assigned_range.
        if self.assigned_range == "empty":
            lower, upper = None, None

        # accommodate a Range object or a python container
        elif isinstance(self.assigned_range, (list, tuple, set)) and len(self.assigned_range) == 2:
            lower, upper = self.assigned_range
        elif hasattr(self.assigned_range, "lower") and hasattr(self.assigned_range, "upper"):
            lower = ensure_timezone_aware(self.assigned_range.lower)
            upper = ensure_timezone_aware(self.assigned_range.upper)

        lower = lower or pytz.utc.localize(datetime.min)
        upper = upper or pytz.utc.localize(datetime.max)

        self.assigned_range = DateTimeTZRange(lower=lower, upper=upper)

        super(SubjectSource, self).save(*args, **kwargs)


class SubjectSourceSummary(SubjectSource):
    class Meta:
        proxy = True
        verbose_name = "Subject Configuration"


class SubjectTypeManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, value):
        return self.get(value=value)

    class Meta:
        verbose_name = _("subject type")
        verbose_name_plural = _("subject types")


def get_default_subject_subtype():
    subject_subtype, created = SubjectSubType.objects.get_or_create(
        value="unassigned", defaults={"display": "Unassigned"}
    )
    return subject_subtype.value


def get_default_subject_type():
    subject_type, created = SubjectType.objects.get_or_create(value="unassigned", defaults={"display": "Unassigned"})
    return subject_type.value


class SubjectType(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(default=uuid.uuid4)
    value = models.CharField(
        primary_key=True,
        max_length=40,
        verbose_name="Subject Type Key",
        unique=True,
        help_text="System key for the subject type",
    )
    display = models.CharField(
        max_length=100, blank=True, verbose_name="Subject Type", help_text=_("Subject Type description")
    )
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    objects = SubjectTypeManager()

    class Meta:
        base_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            ),
        ]
        indexes = [
            Index(fields=["das_tenant", "value"]),
        ]

    def __str__(self):
        return self.display

    def natural_key(self):
        return (self.value,)


class SubjectSubTypeManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, value):
        obj = self.get(value=value)
        return obj

    class Meta:
        verbose_name = _("subject sub-type")
        verbose_name_plural = _("subject sub-types")


class SubjectSubType(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(default=uuid.uuid4)
    value = models.CharField(
        primary_key=True,
        max_length=40,
        verbose_name="Sub-Type Key",
        unique=True,
        help_text="System key for the sub-type",
    )

    display = models.CharField(
        help_text=_("Subject Sub-Type description"), max_length=100, blank=True, verbose_name="Subject Sub-Type"
    )
    subject_type = TenantForeignKey(SubjectType, null=False, on_delete=models.PROTECT)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    ordernum = models.SmallIntegerField(blank=True, null=True)
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "value"],
                name="%(app_label)s_%(class)s_unique_value_across_tenants",
            ),
        ]
        indexes = [
            Index(fields=["das_tenant", "value"]),
        ]

    objects = SubjectSubTypeManager()

    def save(self, *args, **kwargs):
        if not self.subject_type_id:
            self.subject_type_id = get_default_subject_type()
        return super().save(*args, **kwargs)

    def __str__(self):
        return str(self.value)

    def natural_key(self):
        return (self.value,)


class SubjectTrackSegmentFilter(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # TODO Should reference SubjectSubTypes model if it gets created...
    subject_subtype = TenantForeignKey(SubjectSubType, on_delete=models.PROTECT)
    speed_KmHr = models.FloatField(default=7.0)
    additional = models.JSONField(default=dict, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    objects = CommonTenantManager()


DEFAULT_SOURCE_GROUP_ID = "654e592c-fc5a-436d-98dd-fd1b36436a85"


class SubjectGroupQuerySet(models.QuerySet, FilterMixin):
    def by_name_search(self, value):
        return self.filter(name__exact=value)


class SubjectGroupManager(HierarchyManager, models.Manager.from_queryset(SubjectGroupQuerySet)):
    use_in_migrations = True

    def get_default(self):
        return self.get(is_default=True)

    def get_by_natural_key(self, name):
        return self.get(**{"name": name})

    def get_nested_groups(self, parent_id: str) -> Set[str]:
        parent = self.get(**{"id": parent_id})
        groups = set(parent.get_descendants())
        groups.add(parent)
        return groups

    def get_non_cyclic_subjectgroups(self, single_sg=False):
        queryset = self.all() if single_sg else self.filter(_parents=None)
        cyclic_sg = get_cyclic_subjectgroup()

        for o in queryset.prefetch_related("children"):
            descendents = [q.id for q in o.get_descendants()]
            if bool(set(descendents) & set(cyclic_sg)):
                queryset = queryset.exclude(id=o.id)
        return queryset


class SubjectGroup(
    TenantHierarchyModel,
    TimestampedModel,
    create_permissionsethierarchy_mixin("observations.SubjectGroupPermissionSet"),
):
    """
    Manage Groups of subjects so that we can easily set permissions on a group
    rather than each individual Subject. Additionally there are requests to
    get a subset of subjects.

    A group can contain other groups as well.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_("name"), max_length=80)
    subjects = models.ManyToManyField(
        "observations.Subject", related_name="groups", blank=True, through="observations.SubjectGroupSubject"
    )
    is_visible = models.BooleanField(
        _("visible"),
        default=True,
        help_text=_("This Subject group is visible in visualizations."),
    )

    is_default = models.BooleanField(
        _("default subject group"),
        default=False,
        help_text=_("This Subject group is the default for new subjects."),
    )
    children = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="_parents",
        through="observations.SubjectGroupChildren",
    )

    objects = SubjectGroupManager()

    def get_all_subjects(self, user=None, active=None, include_from_subgroups=True, mou_expiry_date=None):
        min_age_days = get_minimum_allowed_age(user) or 0 if user else 0

        queryset = (
            Subject.objects.all()
            .annotate_with_subjectstatus(delay_hours=min_age_days * 24, mou_expiry_date=mou_expiry_date)
            .select_related("subject_subtype__subject_type")
        )
        if active is not None:
            queryset = queryset.by_is_active(active=active).order_by("name")

        if include_from_subgroups:
            """Including descendant group subjects"""
            sg_all = {self}
            sg_all.update(set(self.get_descendants()))
            queryset = queryset.filter(groups__in=sg_all)
        else:
            queryset = queryset.filter(groups=self)

        return queryset.distinct()

    def natural_key(self):
        return (self.name,)

    class Meta:
        verbose_name = _("subject group")
        verbose_name_plural = _("subject groups")
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "is_default"],
                condition=Q(is_default=True),
                name="%(app_label)s_%(class)s_tenant_is_default_unique",
            ),
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            ),
        ]
        indexes = [Index(fields=["das_tenant", "name"])]

    def __str__(self):
        return self.name

    @property
    def auto_permissionset_name(self):
        return _("View {} Subject Group").format(self.name)


SubjectGroupChildren = create_tenanthierarchychildren_model(SubjectGroup)


class SubjectQuerySet(models.QuerySet, FilterMixin):
    def by_region(self, region, **kwargs):
        subjects = self.filter(additional__region=region.region)
        subjects.filter(additional__country=region.country, **kwargs)
        return subjects

    def by_user_subjects_not_distinct(self, user, include_linked=False):
        # Avoid checking for a user that does not have permission sets (ex.
        # AnonymousUser)
        if not hasattr(user, "get_all_permission_sets"):
            return self.none()

        if user.is_superuser:
            return self.all()

        allowed_subject_groups = SubjectGroup.objects.all().filter(permission_sets__in=user.get_all_permission_sets())

        effective_subject_group_set = set()
        for subject_group in allowed_subject_groups:
            effective_subject_group_set.add(subject_group)
            effective_subject_group_set.update(subject_group.get_descendants())

        if include_linked:
            return self.filter(Q(groups__in=effective_subject_group_set) | Q(linked_user=user))
        return self.filter(groups__in=effective_subject_group_set)

    def by_user_subjects(self, user):
        queryset = self.by_user_subjects_not_distinct(user)
        return queryset.distinct("id")

    def by_user_subjects_and_linked(self, user):
        # this coud be done in self.by_user_subjects_not_distinct
        queryset = self.by_user_subjects_not_distinct(user, True)

        return queryset.distinct("id")

    def by_linked_user(self, user):
        if hasattr(user, "linked_subject"):
            return self.filter(id=user.linked_subject.id)

        return self.none()

    def annotate_with_subjectstatus(self, delay_hours=0, mou_expiry_date=None):
        if not mou_expiry_date:
            annotate_subject_status = self.annotate(
                s1=FilteredRelation("subjectstatus", condition=Q(subjectstatus__delay_hours=delay_hours))
            )
        else:
            annotate_subject_status = self.annotate(
                s1=FilteredRelation(
                    "subjectstatus",
                    condition=Q(
                        subjectstatus__delay_hours=delay_hours,
                        subjectstatus__recorded_at__lte=mou_expiry_date,
                    ),
                )
            )
        return (
            annotate_subject_status.annotate(status_recorded_at=F("s1__recorded_at"))
            .annotate(status_last_voice_call_start_at=F("s1__last_voice_call_start_at"))
            .annotate(status_radio_state=F("s1__radio_state"))
            .annotate(status_radio_state_at=F("s1__radio_state_at"))
            .annotate(status_location=F("s1__location"))
            .annotate(
                status_device_status_properties=KeyTransform(
                    "device_status_properties",
                    F("s1__additional"),
                    output_field=models.JSONField(),
                )
            )
        )

    def _query_string_for_filter(self, updated_since=None, updated_until=None):
        updated_since_filter = (
            Q(updated_at__gte=updated_since)
            | Q(status_recorded_at__gte=updated_since)
            | Q(status_last_voice_call_start_at__gte=updated_since)
            | Q(status_radio_state_at__gte=updated_since)
        )

        updated_until_filter = (
            Q(updated_at__lte=updated_until)
            | Q(status_recorded_at__lte=updated_until)
            | Q(status_last_voice_call_start_at__lte=updated_until)
            | Q(status_radio_state_at__lte=updated_until)
        )

        if updated_since and updated_until:
            return updated_since_filter, updated_until_filter
        elif updated_since:
            return updated_since_filter
        elif updated_until:
            return updated_until_filter

    def by_updated_since(self, updated_since):
        updated_since_filter = self._query_string_for_filter(updated_since=updated_since)

        return self.filter(updated_since_filter)

    def by_updated_until(self, updated_until):
        updated_until_filter = self._query_string_for_filter(updated_until=updated_until)
        return self.filter(updated_until_filter)

    def by_updated_since_until(self, updated_since, updated_until):
        updated_since_filter, updated_until_filter = self._query_string_for_filter(
            updated_since=updated_since, updated_until=updated_until
        )
        return self.filter(updated_since_filter, updated_until_filter)

    def by_bbox(self, bbox, last_days=None, include_stationary_subjects=False, updated_since=None, updated_until=None):
        """
        Filter by bbox, last_days.
        Conditionally include subjects that have the latest positions within the bbox but outside the time frame
        indicated by last_days.

        :param updated_until:
        :param updated_since:
        :param bbox:
        :param last_days:
        :param include_stationary_subjects:
        :return: queryset of Subjects.
        """
        geom = Polygon.from_bbox(bbox)
        sources = Observation.objects.filter(location__within=geom)
        sources = sources.exclude(
            source__subjectsource__subject__subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE
        )

        if updated_since and updated_until:
            gt = updated_since
            lt = updated_until
            date_range = DateTimeTZRange(lower=updated_since, upper=updated_until)
            sources = sources.filter(recorded_at__range=(gt, lt))
        elif updated_since:
            gt = updated_since
            sources = sources.filter(recorded_at__gte=gt)
            date_range = DateTimeTZRange(lower=updated_since)
        elif updated_until:
            lt = updated_until
            sources = sources.filter(recorded_at__lte=lt)
            date_range = DateTimeTZRange(upper=updated_until)
        elif last_days:
            lt = datetime.now(tz=pytz.UTC)
            gt = lt - last_days
            # clock skew, server could be behind
            lt = lt + timedelta(minutes=10)
            sources = sources.filter(recorded_at__range=(gt, lt))
            date_range = DateTimeTZRange(lower=gt, upper=lt)

        sources = sources.values("source").annotate(models.Count("source")).values("source")

        subject_sources = SubjectSource.objects.filter(
            source__in=sources,
            assigned_range__overlap=date_range,
        )
        subjects = subject_sources.values("subject")

        if include_stationary_subjects:
            stationary_subjects = Subject.objects.filter(
                subjectstatus__delay_hours=0,
                is_active=True,
                subjectsource__location__within=geom,
                subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE,
            )
            return self.filter(Q(pk__in=subjects) | Q(pk__in=stationary_subjects))
        else:
            return self.filter(pk__in=subjects)

    def by_bbox_last_known_locations(
        self,
        bbox,
        last_days=None,
        include_stationary_subjects=False,
        updated_since=None,
        updated_until=None,
    ):
        geometry = Polygon.from_bbox(bbox)
        queryset = self.filter(
            Q(subjectstatus__location__within=geometry) | Q(subjectsource__location__within=geometry),
            subjectstatus__delay_hours=0,
            subjectstatus__subject__is_active=True,
        )

        if updated_since and updated_until:
            queryset = queryset.filter(subjectstatus__recorded_at__range=(updated_since, updated_until))
        elif updated_since:
            queryset = queryset.filter(subjectstatus__recorded_at__gte=updated_since)
        elif updated_until:
            queryset = queryset.filter(subjectstatus__recorded_at__lte=updated_until)
        elif last_days:
            now = datetime.now(tz=pytz.UTC)
            since = now - last_days
            until = now + timedelta(minutes=10)
            queryset = queryset.filter(subjectstatus__recorded_at__range=(since, until))

        if not include_stationary_subjects:
            result = queryset.exclude(subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE)
            return result
        return queryset

    def get_staff(self):
        return self.filter(subject_subtype__subject_type__value="person")

    def by_groups(self, subject_groups):
        return self.filter(groups__in=subject_groups)

    def by_group(self, subject_group_id):
        return self.filter(groups__id=subject_group_id)

    def by_is_active(self, active=True):
        return self.filter(is_active=active)

    def by_name_search(self, value):
        return self.filter(name__icontains=value)

    def by_subjectgroups(self, subject_groups, user):
        if not hasattr(user, "get_all_permission_sets"):
            return self.none()

        if user.is_superuser:
            return self.filter(groups__in=subject_groups).distinct("id")

        allowed_subject_groups = subject_groups.filter(permission_sets__in=user.get_all_permission_sets())
        if allowed_subject_groups.exists():
            return self.filter(groups__in=allowed_subject_groups).distinct("id")

        if user.has_linked_subject:
            allowed_subject_groups = subject_groups & user.linked_subject.groups.all()
            return (self.filter(groups__in=allowed_subject_groups) & self.by_linked_user(user)).distinct("id")

        return self.none()

    def by_linked_user_id(self, user_id: str):
        try:
            user = User.objects.get(id=user_id)
            return user.linked_subject
        except ObjectDoesNotExist:
            return None


class SubjectManager(TenantManagerMixin, models.Manager.from_queryset(SubjectQuerySet)):
    use_in_migrations = True

    def create_subject(self, **kwargs):
        # all subjects are added to the default subject group
        subject_groups = kwargs.pop("subject_groups", []) or []
        subject = super().create(**kwargs)
        if subject_groups:
            for group in subject_groups:
                if not isinstance(group, SubjectGroup):
                    group, created = SubjectGroup.objects.get_or_create(name=group)
                subject.groups.add(group)
        else:
            subject.groups.set((SubjectGroup.objects.get_default(),))

        return subject

    def get_subjects_from_observation_id(self, observation_id, values=None):
        """
        Convenient place to keep rules for identifying a Subject(s) related to an observation.
        :param observation_id:
        :return:
        """
        subjects = Subject.objects.filter(
            subjectsource__source__observation__id=observation_id,
            subjectsource__assigned_range__contains=F("subjectsource__source__observation__recorded_at"),
        )
        if values:
            subjects = subjects.values(*values)
        return subjects

    def get_current_subjects_from_source_id(self, source_id, values=None, dt=None):
        """
        Convenient place to keep rules for identifying a Subject(s) related to a Source.
        :param source_id:
        :param values: Caller can indicate to return values using a set.
        :param dt: Call can specify the date to use to find subjects assigned to the source. Default is 'now'.
        :return: a queryset (or values) for assigned Subjects.
        """

        dt = dt or datetime.now(tz=pytz.utc)

        subjects = Subject.objects.filter(
            subjectsource__source__id=source_id, subjectsource__assigned_range__contains=dt
        )

        if values:
            subjects = subjects.values(*values)
        return subjects


SEX_MALE = "male"
SEX_FEMALE = "female"
SEX_UNKNOWN = "unknown"
SEX_EMPTY = ""
SEX_CHOICES = (
    (SEX_EMPTY, _("")),
    (SEX_MALE, _("Male")),
    (SEX_FEMALE, _("Female")),
    (SEX_UNKNOWN, _("Unknown")),
)


class Subject(TenantModelMixin, TimestampedModel, PermissionSetGroupMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(_("name"), max_length=100)
    owner = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subjects",
        related_query_name="subject",
    )
    linked_user = TenantOneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_subject",
    )
    additional = models.JSONField("additional data", default=dict, blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("This subject is actively shown in visualizations."),
    )
    common_name = TenantForeignKey("observations.CommonName", on_delete=models.PROTECT, blank=True, null=True)
    subject_subtype = TenantForeignKey(SubjectSubType, on_delete=models.PROTECT)
    import_gpx_data = TenantForeignKey("observations.GPXTrackFile", on_delete=models.SET_NULL, null=True, blank=True)

    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = SubjectManager()
    tenant_id = "das_tenant_id"

    @property
    def subject_type(self):
        return self.subject_subtype.subject_type.value

    @property
    def is_stationary_subject(self):
        return self.subject_type == STATIONARY_SUBJECT_VALUE

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        permissions = (
            ("view_last_position", "Permission to view the last reported position of a Subject only."),
            ("view_real_time", "Access to real-time observations."),
            ("view_delayed", "Access to a 24 hour delayed observation feed. No real-time or last reported position."),
            ("subscribe_alerts", "Permission to subscribe to an alert on this Subject."),
            (
                "change_alerts",
                "Permission to configure alerts for subject, includes setting geofences, proximity and immobility settings.",
            ),
            ("change_view", "An admin permission to change which users can view a Subject and their view permission."),
            ("access_begins_7", "Can view tracks no more than 7 days old"),
            ("access_begins_16", "Can view tracks no more than 16 days old"),
            ("access_begins_30", "Can view tracks no more than 30 days old"),
            ("access_begins_60", "Can view tracks no more than 60 days old"),
            ("access_begins_all", "Can view all historical tracks"),
            ("access_ends_0", "Can view tracks no less than 0 days old"),
            ("access_ends_1", "Can view tracks no less than 1 day old"),
            ("access_ends_3", "Can view tracks no less than 3 days old"),
            ("access_ends_7", "Can view tracks no less than 7 days old"),
        )
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "linked_user"],
                name="%(app_label)s_%(class)s_unique_across_tenants",
            )
        ]

    @property
    def color(self):
        color = self.additional.get("rgb", DEFAULT_COLOR)
        if color:
            color = to_rgb(color)
        return color

    def clean(self):
        if self.name != escape(self.name):
            raise ValidationError({"name": _("Invalid name. Please remove special characters and try again.")})

    def clean_fields(self, exclude=None):
        return super().clean_fields(exclude)

    @cached_property
    def source(self):
        subject_source = (
            SubjectSource.objects.select_related("source", "source__provider")
            .filter(subject_id=self.pk)
            .order_by("-assigned_range")
            .first()
        )

        return subject_source.source

    def get_track(self, user, since, until, limit):
        since, until, limit = calculate_track_range(user, since, until, limit)

        qs = Observation.objects.get_subject_observations_values(self, since=since, until=until, limit=limit)

        qs = list(qs)
        return [o["location"].coords for o in qs], [zeroout_microseconds(o["recorded_at"]) for o in qs]

    def observations(self, last_hours=None, until=None):
        """returns all observations for this Subject, spanning
        Sources as necessary"""
        since = None

        if last_hours:
            if not until:
                until = datetime.now(tz=pytz.UTC)
            since = until - timedelta(hours=last_hours)

        return Observation.objects.get_subject_observations(self, since=since, until=until)

    def default_trajectory_filter(self):
        # Get trajectory filter based on subject. Might not exist.
        try:
            return SubjectTrackSegmentFilter.objects.filter(subject_subtype=self.subject_subtype.value).first()
        except SubjectTrackSegmentFilter.DoesNotExist:
            pass

    def create_trajectory(self, obs=None, trajectory_filter_params=None):
        """
        Hydrate the trajectory
        """

        if obs is None:
            obs = self.observations()

        def create_fix(observation):
            gp = pymet.base.GeoPoint(observation.location.x, observation.location.y, 0.0)
            fix = pymet.base.Fix(gp, observation.recorded_at)
            return fix

        # Create a relocations object
        fixes = [create_fix(x) for x in obs]
        relocs = pymet.base.Relocations(fixes=fixes)

        # Filter the relocations for junk coordinates
        coord_filter = pymet.base.RelocsCoordinateFilter()
        relocs.apply_fix_filter(coord_filter)

        # Create a trajectory from the relocations
        traj = pymet.base.Trajectory(relocs)

        if trajectory_filter_params is not None:
            speed_threshold = trajectory_filter_params.speed_KmHr

            # Create a relocations speed filter
            speed_filter = pymet.base.RelocsSpeedFilter(max_speed_kmhr=speed_threshold)
            traj.relocs.apply_fix_filter(speed_filter)

            # Create a trajseg filter
            traj_filt = pymet.base.TrajSegFilter(max_speed_kmhr=speed_threshold)
            traj.traj_seg_filter = traj_filt
        setattr(traj, "subject", self)
        return traj

    @property
    def image_url(self):
        image_url = static_image_finder.get_marker_icon(self._image_keys())
        if not image_url:
            image_url = "/static/pin-black.svg"
        return image_url

    @property
    def kml_image_url(self):
        image_url = static_image_finder.get_marker_icon(self._image_keys(), image_types=("png", "jpg"))
        if not image_url:
            image_url = "/static/pin.png"
        return image_url

    def _image_keys(self):
        """return the preferred key first"""
        key = self.subject_subtype.value.lower()
        sex = self.additional.get("sex", SEX_MALE)
        for sex in (sex, SEX_MALE):
            yield "-".join((key, "black", sex.lower()))
            yield "-".join((key, sex.lower()))

        try:
            state = (
                getattr(self, "status_radio_state", None)
                or self.subjectstatus_set.filter(delay_hours=0).last().radio_state
            )
        except (SubjectStatus.DoesNotExist, AttributeError):
            yield "-".join((key, "black"))
            yield key
        else:
            color = STATUS_COLORS.get(state, "black")
            yield "-".join((key, color))
            yield key

    def get_users_to_notify(self):
        """
        return a queryset of all users to be notified for this subject
        :return:
        """
        if not self.groups:
            return []
        else:
            users = set()
            ps_ids = self.get_obj_permission_set_ids()
            for ps in PermissionSet.objects.filter(id__in=ps_ids):
                users.update(ps.user_set.all())
            return users

    def get_ancestor_subject_groups(self):
        """
        Return a set of all unique ancestor Subject Groups who have access to
        the current subject based on hierarchy.
        :return:
        """
        subject_groups = set()
        for subject_group in self.groups.all():
            subject_groups.add(subject_group)
            subject_groups = subject_groups.union(set(subject_group.get_ancestors()))
        return subject_groups

    def save(self, *args, **kwargs):
        if not self.subject_subtype_id:
            self.subject_subtype_id = get_default_subject_subtype()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}"  # ({self.subject_subtype.display})'


class SubjectGroupSubjectManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, subjectgroup, subject):
        return self.get(subjectgroup=subjectgroup, subject=subject)


class SubjectGroupSubject(TenantModelMixin, UUIDModel):
    subjectgroup = TenantForeignKey(SubjectGroup, on_delete=models.CASCADE)
    subject = TenantForeignKey(Subject, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="observations_subjectgroupsubject",
    )
    tenant_id = "das_tenant_id"

    objects = SubjectGroupSubjectManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def natural_key(self):
        return (self.subjectgroup, self.subject)


class SubjectGroupPermissionSetManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, subjectgroup, permissionset):
        return self.get(subjectgroup=subjectgroup, permissionset=permissionset)


class SubjectGroupPermissionSet(TenantModelMixin, UUIDModel):
    subjectgroup = TenantForeignKey(SubjectGroup, on_delete=models.CASCADE)
    permissionset = TenantForeignKey(PermissionSet, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="observations_subjectgrouppermissionset",
    )
    tenant_id = "das_tenant_id"

    objects = SubjectGroupPermissionSetManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "subjectgroup", "permissionset"],
                name="%(app_label)s_%(class)s_tenant_from_to_unique",
            ),
        ]

    def natural_key(self):
        return (self.subjectgroup, self.permissionset)


class SourceGroupSourceManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, sourcegroup, source):
        return self.get(sourcegroup=sourcegroup, source=source)


class SourceGroupSource(TenantModelMixin, UUIDModel):
    sourcegroup = TenantForeignKey(SourceGroup, on_delete=models.CASCADE)
    source = TenantForeignKey(Source, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="observations_sourcegroupsource",
    )
    tenant_id = "das_tenant_id"

    objects = SourceGroupSourceManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def natural_key(self):
        return (self.sourcegroup, self.source)


class SourceGroupPermissionSetManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, sourcegroup, permissionset):
        return self.get(sourcegroup=sourcegroup, permissionset=permissionset)


class SourceGroupPermissionSet(TenantModelMixin, UUIDModel):
    sourcegroup = TenantForeignKey(SourceGroup, on_delete=models.CASCADE)
    permissionset = TenantForeignKey(PermissionSet, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="observations_sourcegrouppermissionset",
    )
    tenant_id = "das_tenant_id"

    objects = SourceGroupPermissionSetManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "sourcegroup", "permissionset"],
                name="%(app_label)s_%(class)s_tenant_from_to_unique",
            ),
        ]

    def natural_key(self):
        return (self.sourcegroup, self.permissionset)


OBSERVATION_DELAY_HRS = 72


class SubjectSummary(Subject):
    class Meta:
        proxy = True
        verbose_name = _("Subject Summary")
        verbose_name_plural = _("Subject Summary")


class SubjectPositionSummary(Observation):
    class Meta:
        proxy = True
        verbose_name = _("Subject Positions")
        verbose_name_plural = _("Subject Positions")


class SubjectStatusQuerySet(models.QuerySet):
    def get_last(self):
        for row in self:
            if row.delay_hours == 0:
                return row

    def get_delayed(self, delay=OBSERVATION_DELAY_HRS):
        for row in self:
            if row.delay_hours == delay:
                return row

    def get_range_endpoints(self, max_delay, min_delay):
        range_start = None
        range_end = None
        for row in self:
            if row.delay_hours > max_delay or row.delay_hours < min_delay:
                continue
            if range_start is None or row.delay_hours > range_start.delay_hours:
                range_start = row
            if range_end is None or row.delay_hours < range_end.delay_hours:
                range_end = row
        return range_start, range_end


DEFAULT_STATUS_VALUE_DATE = datetime(1970, 1, 1, tzinfo=pytz.utc)
DEFAULT_STATUS_VALUE_LOCATION = EMPTY_POINT


class SubjectStatusManager(TenantManagerMixin, models.Manager.from_queryset(SubjectStatusQuerySet)):
    use_in_migrations = True

    DEFAULT_STATUS_VALUES = {
        "location": DEFAULT_STATUS_VALUE_LOCATION,
        "recorded_at": DEFAULT_STATUS_VALUE_DATE,
        "radio_state_at": DEFAULT_STATUS_VALUE_DATE,
        "additional": {"device_status_properties": None},
    }

    # Delayed windows include all but 'current'.
    delayed_windows = list((item for item in VIEW_END_WINDOWS if item[1] > 0))

    @staticmethod
    def update_current_from_source(source, include_empty_location: bool = False):
        observation = Observation.objects.get_last_source_observation(source, include_empty_location)
        if not observation:
            return

        update_subject_status_from_observation(observation)

    @staticmethod
    def update_current_from_deleted_observation(deleted_observation):
        """
        Only update SubjectStatus if the *deleted* observation was apparently the latest for the source.

        :param deleted_observation: Observation instance that was deleted.
        """
        latest_observation = Observation.objects.get_last_source_observation(deleted_observation.source)

        if latest_observation and latest_observation.recorded_at < deleted_observation.recorded_at:
            update_subject_status_from_observation(latest_observation, force=True)

    def update_current(self, subject):
        for subject_source in SubjectSource.objects.filter(
            subject=subject, assigned_range__contains=datetime.now(tz=pytz.utc)
        ):
            self.update_current_from_source(
                subject_source.source,
                include_empty_location=is_subject_stationary_subject(subject),
            )

    def update_delayed_status(self, subject):
        """
        For a given subject, update its SubjectStatus Records.
        :param subject:
        :return:
        """
        # Initialize the loop with the most recent 'delayed' observation.
        key, delay_days = self.delayed_windows[0]
        delay_hours = delay_days * 24
        until = datetime.now(tz=pytz.utc) - timedelta(hours=delay_hours)
        observation = Observation.objects.get_subject_observations(subject=subject, until=until, limit=1).first()

        # March through the view windows.
        for key, delay_days in self.delayed_windows:
            if not observation:  # No more work to be done.
                return

            delay_hours = delay_days * 24
            until = datetime.now(tz=pytz.utc) - timedelta(hours=delay_hours)

            if observation.recorded_at <= until:
                # Update using the current observation until it's no longer
                # valid.
                update_subject_status_from_observation(observation, delay_hours=delay_hours)
            else:
                # Refresh the 'latest observation' for the given window.
                observation = Observation.objects.get_subject_observations(
                    subject=subject, until=until, limit=1
                ).first()
                if observation:
                    update_subject_status_from_observation(observation, delay_hours=delay_hours)

    def ensure_for_subject(self, subject):
        for delay_hours in VIEW_END_WINDOWS:
            SubjectStatus.objects.get_or_create(
                subject=subject, delay_hours=delay_hours[1] * 24, defaults=SubjectStatusManager.DEFAULT_STATUS_VALUES
            )

    def get_current_status(self, subject):
        value, created = SubjectStatus.objects.get_or_create(
            subject=subject, delay_hours=0, defaults=SubjectStatusManager.DEFAULT_STATUS_VALUES
        )
        return value

    def maintain_subject_status(self, subject_id):
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            logger.warning("Cannot find Subject with id: %s", subject_id)
        else:
            logger.info("SubjectStatus maintenance for Subject: %s, id: %s", subject.name, subject_id)
            self.ensure_for_subject(subject)
            self.update_current(subject)
            self.update_delayed_status(subject)


def build_updates(
    recorded_at,
    location,
    radio_state=None,
    radio_state_at=None,
    last_voice_call_start_at=None,
    location_requested_at=None,
    force=False,
):
    """
    Build conditional updates for SubjectStatus Record..
    """

    # Ignore radio_state values if we're forcing this update.
    if force:
        radio_state = last_voice_call_start_at = location_requested_at = radio_state_at = None

    conditional_updates = {
        "recorded_at": Value(recorded_at) if force else Greatest(F("recorded_at"), Value(recorded_at)),
        "location": (
            location
            if force
            else Case(
                When(recorded_at__lte=Value(recorded_at), then=Value(str(location))),
                default=F("location"),
                output_field=models.PointField(),
            )
        ),
    }

    if radio_state_at and radio_state:
        conditional_updates["radio_state"] = Case(
            When(radio_state_at__lte=Value(radio_state_at), then=Value(radio_state)),
            default=F("radio_state"),
            output_field=dbmodels.CharField(),
        )

        conditional_updates["radio_state_at"] = Greatest(
            F("radio_state_at"), Value(radio_state_at), output_field=dbmodels.DateTimeField()
        )

    if last_voice_call_start_at:
        conditional_updates["last_voice_call_start_at"] = Greatest(
            F("last_voice_call_start_at"), Value(last_voice_call_start_at), output_field=dbmodels.DateTimeField()
        )

    if location_requested_at:
        conditional_updates["location_requested_at"] = Greatest(
            F("location_requested_at"), Value(location_requested_at), output_field=dbmodels.DateTimeField()
        )

    return conditional_updates


def update_subject_status(
    source,
    recorded_at,
    location,
    last_voice_call_start_at=None,
    location_requested_at=None,
    radio_state=None,
    radio_state_at=None,
    reported_subject_name=None,
    transformed_additional_data=None,
    delay_hours=0,
    force=False,
):
    status_updates = build_updates(
        recorded_at=recorded_at,
        location=location,
        radio_state=radio_state,
        radio_state_at=radio_state_at,
        last_voice_call_start_at=last_voice_call_start_at,
        location_requested_at=location_requested_at,
        force=force,
    )

    if reported_subject_name:
        status_updates["additional"] = {"subject_name": reported_subject_name}

    if transformed_additional_data is not None:
        status_updates.setdefault("additional", {})["device_status_properties"] = transformed_additional_data

    SubjectStatus.objects.filter(
        subject__subjectsource__source=source,
        subject__subjectsource__assigned_range__contains=recorded_at,
        delay_hours=delay_hours,
    ).update(**status_updates)

    if reported_subject_name and delay_hours == 0:
        Subject.objects.filter(
            subjectsource__assigned_range__contains=recorded_at, subjectsource__source=source
        ).exclude(name=reported_subject_name).update(name=reported_subject_name)


def transform_additional_data(additional, transform_format):
    """Transform additional subject data for display."""

    if not transform_format or not isinstance(transform_format, (list, tuple)):
        return None

    device_attributes = []
    dests = []
    for tf in transform_format:
        ds = tf.get("dest")

        keys = []
        for k in tf.get("source").split("."):
            if k not in ["", "additional"]:
                index = re.search(r"\[([0-9]+)]", k)
                if index:
                    keys.append(int(index.group(1)))
                else:
                    keys.append(k)

        try:
            value = reduce(getitem, keys, additional)
        except KeyError:
            continue

        if value is not None and ds not in dests:
            if isinstance(value, dict):  # list-ify a dict
                value = [f"{k}:{str(v)}" for k, v in value.items()]

            if isinstance(value, list):  # string-ify a list
                value = ",".join([str(x) for x in value])

            metadata = dict(value=value, label=tf.get("label"), units=tf.get("units"))
            dests.append(ds)
            device_attributes.append(metadata)
    return device_attributes


def update_subject_status_from_observation(observation, delay_hours=0, force=False):
    additional = observation.additional
    transformed_data = None

    try:
        last_voice_call_start_at = parse_date(additional["last_voice_call_start_at"])
    except:
        last_voice_call_start_at = None

    try:
        location_requested_at = parse_date(additional["location_requested_at"])
    except:
        location_requested_at = None

    recorded_at = observation.recorded_at
    source = observation.source
    location = observation.location
    if additional:
        reported_subject_name = additional.get("subject_name")

        radio_state = observation.additional.get("radio_state")
        try:
            radio_state_at = parse_date(observation.additional.get("radio_state_at"))
        except:
            radio_state_at = None

        try:
            transformed_data = transform_additional_data(additional, source.provider.transforms)
        except Exception as exc:
            logger.debug(f"failed with exception {exc}")

    else:
        reported_subject_name, radio_state, radio_state_at = None, None, None

    update_subject_status(
        source=source,
        location=location,
        recorded_at=recorded_at,
        last_voice_call_start_at=last_voice_call_start_at,
        location_requested_at=location_requested_at,
        radio_state=radio_state,
        radio_state_at=radio_state_at,
        reported_subject_name=reported_subject_name,
        transformed_additional_data=transformed_data,
        delay_hours=delay_hours,
        force=force,
    )

    # Ordinarily this will not be required, because an Observation signal will
    # trigger a notify. In the case of force, it is likely we're handling
    # an Observation.delete.
    if force:
        logger.debug("Notifying for subject status update source: %s, recorded_at: %s", source, recorded_at)
        transaction.on_commit(lambda: notify_all_subjectstatus_updates(source, recorded_at))


def update_subject_status_from_post(source, recorded_at, location, additional):
    """
    Intention is to update latest SubjectStatus record under the case where a redundant GPS fix has been posted.
    """

    radio_state = additional.get("radio_state", SubjectStatus.UNKNOWN)

    try:
        radio_state_at = parse_date(additional.get("radio_state_at"))
    except:
        radio_state_at = None

    try:
        last_voice_call_start_at = parse_date(additional["last_voice_call_start_at"])
    except:
        last_voice_call_start_at = None

    try:
        location_requested_at = parse_date(additional["location_requested_at"])
    except:
        location_requested_at = None

    location = Point(x=location["longitude"], y=location["latitude"], srid=4326)
    reported_subject_name = additional.get("subject_name")

    update_subject_status(
        source=source,
        location=location,
        recorded_at=recorded_at,
        last_voice_call_start_at=last_voice_call_start_at,
        location_requested_at=location_requested_at,
        radio_state=radio_state,
        radio_state_at=radio_state_at,
        reported_subject_name=reported_subject_name,
    )

    transaction.on_commit(lambda: notify_all_subjectstatus_updates(source, recorded_at))


def notify_all_subjectstatus_updates(source, recorded_at):
    logger.debug("Looking for subjects for notify_subjectstatus_update. source_id=%s", source.id)

    for subject in Subject.objects.filter(
        subjectsource__source=source, subjectsource__assigned_range__contains=recorded_at
    ):
        logger.debug("Sending notify_subjectstatus_update. subject_id=%s", subject.id)
        notify_subjectstatus_update(subject.id)


class CommonNameManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, value):
        return self.get(**{value: value})


class CommonName(TenantModelMixin, TimestampedModel):
    """Common name for an animal, could stretch this to other subtypes as well."""

    subject_subtype = TenantForeignKey(SubjectSubType, on_delete=models.PROTECT, default=get_default_subject_subtype)
    value = models.CharField(primary_key=True, max_length=100)
    display = models.CharField(max_length=100)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = CommonNameManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            UniqueConstraint(fields=["das_tenant", "value"], name="%(app_label)s_%(class)s_tenant_value_unique"),
        ]

    def __str__(self):
        return self.display


def generate_subject_status_serial_number():
    return get_next_int_val("observations", "SubjectStatus", "serial_number")


class SubjectStatus(TenantModelMixin, PermissionSetGroupMixin, TimestampedModel, UUIDModel):
    ONLINE_GPS = "online-gps"
    ONLINE = "online"
    OFFLINE = "offline"
    ALARM = "alarm"
    UNKNOWN = "na"
    RADIO_STATE_CHOICES = (
        (ONLINE_GPS, "Online w/GPS"),
        (ONLINE, "Online"),
        (OFFLINE, "Offline"),
        (ALARM, "Alarm"),
        (UNKNOWN, "Unknown"),
    )
    RADIO_STATE_CHOICES = (
        (ONLINE_GPS, "online-gps"),
        (ONLINE, "online"),
        (OFFLINE, "offline"),
        (ALARM, "alarm"),
        (UNKNOWN, "n/a"),
    )
    serial_number = models.IntegerField(null=False, verbose_name="Serial Number")
    subject = TenantForeignKey("Subject", on_delete=models.CASCADE)
    location = models.PointField("location")
    recorded_at = models.DateTimeField(
        "location at",
    )
    delay_hours = models.IntegerField("delay in hours")
    additional = models.JSONField("additional", blank=True, default=dict)

    radio_state = models.CharField("state", null=False, choices=RADIO_STATE_CHOICES, default=UNKNOWN, max_length=20)
    radio_state_at = models.DateTimeField("Time of state", null=True, blank=True)
    last_voice_call_start_at = models.DateTimeField("Last time voice call was initiated", null=True, blank=True)
    location_requested_at = models.DateTimeField("Last time location was requested", null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = SubjectStatusManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = _("Subject Status")
        verbose_name_plural = _("Subject Status")
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "subject", "delay_hours"], name="%(app_label)s_%(class)s_tenant_subject_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.serial_number = generate_subject_status_serial_number()
        super().save(*args, **kwargs)

    @property
    def groups(self):
        return self.subject.groups


class SubjectStatusLatestManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_queryset(self):
        return super().get_queryset().filter(delay_hours=0)


class SubjectStatusLatest(SubjectStatus):
    objects = SubjectStatusLatestManager()

    class Meta:
        proxy = True


class Region(TenantModelMixin, models.Model):
    """Region of Africa a subject is in"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    slug = models.SlugField("unique id", max_length=100)
    region = models.CharField("region or pa", max_length=100)
    country = models.CharField("country mostly containing region", max_length=100)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "slug"],
                name="%(app_label)s_%(class)s_unique_slug_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "slug"], name="%(app_label)s_%(class)s_slug_idx")]

    def __str__(self):
        return "%s, %s" % (self.region, self.country)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.region + " " + self.country)
        super(Region, self).save(*args, **kwargs)


class QuerySetOnSharedConnection(models.QuerySet, SharedResourceHandler):
    def aquire_resource(self):
        logger.debug("Aquire database connection from %s", self.__class__.__name__)
        connection = connections[self.db]
        connection.inc_thread_sharing()

    def release_resource(self):
        connection = connections[self.db]
        connection.dec_thread_sharing()
        logger.debug("Release database connection from %s", self.__class__.__name__)

    def report_error(self, failure):
        logger.warning("A failure occurred on shared connection: %s", failure)

    @use_shared_resource
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    @use_shared_resource
    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)


class SocketClientManager(TenantManagerMixin, models.Manager.from_queryset(QuerySetOnSharedConnection)):
    use_in_migrations = True


class SocketClient(TenantModelMixin, TimestampedModel):
    """
    Associate a socket ID with a user and a set of session-related data.
    """

    sid = models.CharField(max_length=40, blank=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, db_column="id")
    username = models.CharField("Das username associated with session", max_length=30)
    bbox = models.MultiPolygonField("Viewport bounding box.", null=True, blank=True)
    event_filter = models.JSONField("Event filter", default=dict)
    patrol_filter = models.JSONField("Patrol filter", default=dict)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = SocketClientManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["das_tenant", "sid"],
                name="%(app_label)s_%(class)s_tenant_sid_unique",
            ),
        ]


class UserSessionManager(TenantManagerMixin, models.Manager.from_queryset(QuerySetOnSharedConnection)):
    use_in_migrations = True


class UserSession(TenantModelMixin, TimestampedModel, SharedResourceHandler):
    sid = models.CharField(max_length=40, blank=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, db_column="id")
    time_range = DateTimeRangeField("user session time", null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = UserSessionManager()
    tenant_id = "das_tenant_id"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["das_tenant", "sid"],
                name="%(app_label)s_%(class)s_tenant_sid_unique",
            ),
        ]

    def aquire_resource(self):
        logger.debug("Aquire database connection from %s", self.__class__.__name__)
        connection = connections[UserSession.objects.db]
        connection.inc_thread_sharing()

    def release_resource(self):
        connection = connections[UserSession.objects.db]
        connection.dec_thread_sharing()
        logger.debug("Release database connection from %s", self.__class__.__name__)

    def report_error(self, failure):
        logger.warning("Could not save the UserSession: %s", failure)

    @use_shared_resource
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


from analyzers.models import ObservationAnnotator  # noqa


class SubjectMaximumSpeed(ObservationAnnotator):
    class Meta:
        proxy = True


class GPXLogRecord(TenantModelMixin, models.Model):
    success = "success"
    pending = "pending"
    failure = "failure"

    PROCESSED_STATUS_CHOICES = [
        (success, "Success"),
        (pending, "Pending"),
        (failure, "Failure"),
    ]

    created_by = TenantForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gpx_track_files",
        related_query_name="gpx_track_file",
    )
    file_name = models.CharField(max_length=225, null=True, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    processed_date = models.DateTimeField(auto_now_add=True)
    points_imported = models.CharField(max_length=225, null=True, blank=True)
    processed_status = models.CharField(choices=PROCESSED_STATUS_CHOICES, max_length=255, null=False, blank=False)
    status_description = models.CharField(max_length=225, null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    class Meta:
        abstract = True


class GPXManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, value):
        return self.get(value=value)

    def get_file(self, gpx_id):
        gpx = self.get(id=gpx_id)
        return gpx.data, gpx.file_name

    def get_source_id(self, gpx_id):
        src_id = self.filter(id=gpx_id).annotate(source_id=F("source_assignment__source__id")).values("source_id")
        return src_id[0].get("source_id")


def upload_to(instance, filename):
    filename = filename.split("/")[-1]
    timestamp = "{:%Y%m%d%H%M}".format(datetime.now(tz=pytz.utc))
    tenant = get_tenant_settings()
    file_path = f"{tenant.slug_name}/{GPX_FILES_FOLDER}/{timestamp}-{filename}"
    return file_path


class GPXTrackFile(GPXLogRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    source_assignment = TenantForeignKey("SubjectSource", on_delete=models.PROTECT)
    description = models.CharField(max_length=255, null=True, blank=True)
    data = models.FileField(upload_to=upload_to, null=True, blank=True)

    objects = GPXManager()

    class Meta:
        verbose_name_plural = "GPX track file"
        ordering = ("processed_date",)


PENDING = "pending"
SENT = "sent"
ERRORED = "errored"
RECEIVED = "received"
MESSAGE_STATE_CHOICES = (
    (PENDING, "Pending"),
    ("sent", "Sent"),
    ("errored", "Errored"),
    ("received", "received"),
)

INBOX = "inbox"
OUTBOX = "outbox"
MESSAGE_TYPES = (
    (INBOX, "Inbox"),
    (OUTBOX, "Outbox"),
)


class MessageFilteringQuerySet(models.QuerySet, FilterMixin):
    def by_subject_ids(self, subject_ids):
        return self.filter(Q(sender_id__in=subject_ids) | Q(receiver_id__in=subject_ids))

    def by_source_id(self, source_id):
        return self.filter(device=source_id)

    def by_read(self, read):
        return self.filter(read=read)

    def by_date_range(self, since, until):
        if not since and not until:
            return self
        if not since:
            return self.filter(message_time__lt=until)
        if not until:
            return self.filter(message_time__gte=since)
        return self.filter(message_time__range=(since, until))


class MessagesManager(TenantManagerMixin, models.Manager.from_queryset(MessageFilteringQuerySet)):
    use_in_migrations = True


class Message(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    _limits = Q(app_label="observations", model="subject") | Q(app_label="accounts", model="user")

    sender_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=_limits,
        null=True,
        blank=True,
        related_name="sender_content_type",
    )
    receiver_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=_limits,
        null=True,
        blank=True,
        related_name="receiver_content_type",
    )
    sender_id = models.UUIDField(null=True, blank=True, default=None)
    receiver_id = models.UUIDField(null=True, blank=True, default=None)
    sender = GenericForeignKey("sender_content_type", "sender_id")
    receiver = GenericForeignKey("receiver_content_type", "receiver_id")
    device = TenantForeignKey("Source", null=True, on_delete=models.SET_NULL)
    message_type = models.CharField(max_length=40, choices=MESSAGE_TYPES, default=OUTBOX)
    text = models.TextField(blank=True)
    status = models.CharField(max_length=40, choices=MESSAGE_STATE_CHOICES, default=PENDING)
    device_location = models.PointField(blank=True, null=True)
    message_time = models.DateTimeField(null=False, blank=False)
    read = models.BooleanField(default=False)
    additional = models.JSONField("additional data", default=dict, blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = MessagesManager()
    tenant_id = "das_tenant_id"

    class Meta:
        indexes = [
            Index(fields=["das_tenant", "-message_time"]),
            Index(fields=["das_tenant", "read"]),
        ]
        index_together = [
            ("das_tenant", "sender_id", "message_time"),
            ("das_tenant", "receiver_id", "message_time"),
        ]
        ordering = ("-message_time",)


class AnnouncementFilteringQuerySet(models.QuerySet, FilterMixin):
    def order_by_announcement_at(self):
        return self.order_by("-announcement_at")

    def by_read(self, state, user):
        """return all announcement read or unread"""
        qs = self.filter(related_users=user) if state else self.filter(~Q(related_users=user))
        return qs


class AnnouncementManager(TenantManagerMixin, models.Manager.from_queryset(AnnouncementFilteringQuerySet)):
    use_in_migrations = True


class Announcement(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    related_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, through="observations.AnnouncementUser"
    )
    title = models.CharField(null=True, max_length=255)
    description = models.TextField(null=True)
    additional = models.JSONField(null=True, blank=True, default=dict)
    link = models.URLField(verbose_name="Link to topic", null=True)
    announcement_at = models.DateTimeField(db_index=True, null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = AnnouncementManager()
    tenant_id = "das_tenant_id"


class AnnouncementUserManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, announcement, user):
        return self.get(announcement=announcement, user=user)


class AnnouncementUser(TenantModelMixin, UUIDModel):
    announcement = TenantForeignKey(Announcement, on_delete=models.CASCADE)
    user = TenantForeignKey(User, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="observations_announcementuser",
    )
    tenant_id = "das_tenant_id"

    objects = AnnouncementUserManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "announcement", "user"],
                name="%(app_label)s_%(class)s_tenant_from_to_unique",
            ),
        ]

    def natural_key(self):
        return (self.announcement, self.user)


class LatestObservationSource(TenantModelMixin, models.Model):
    """Manage/keep the latest observation of each source.
    The CRUD operations are managed by database triggers."""

    source = TenantForeignKey(
        "Source",
        on_delete=models.CASCADE,
        primary_key=True,
        unique=True,
        related_name="last_observation_sources",
        related_query_name="last_observation_source",
    )
    observation = TenantForeignKey("Observation", on_delete=models.CASCADE)
    recorded_at = models.DateTimeField()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"

    objects = CommonTenantManager()

    class Meta:
        constraints = [
            UniqueConstraint(fields=["das_tenant", "source"], name="%(app_label)s_%(class)s_tenant_source_unique"),
        ]
