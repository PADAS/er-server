import logging
import uuid

from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantModelMixin

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import Index, UniqueConstraint
from django.utils.translation import gettext_lazy as _

from activity.models import Event
from core.models import DASTenant, TimestampedModel
from observations.models import Observation, Subject, SubjectGroup
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager
from utils.tenant.models import TenantThroughModel

logger = logging.getLogger(__name__)

# Result levels.
OK = 10
WARNING = 20
CRITICAL = 30
ERROR = 40

EVENT_PRIORITY_MAP = {
    CRITICAL: Event.PRI_URGENT,
    WARNING: Event.PRI_IMPORTANT,
    OK: Event.PRI_REFERENCE,
}


class SubjectAnalyzerConfig(TenantModelMixin, TimestampedModel):
    """
    An implementation of SubjectAnalyzerConfig is meant to associate a specific set of parameter values with
    a SubjectGroup that it applies to.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(
        null=False,
        max_length=100,
        verbose_name=_("Analyzer Name"),
        help_text=_("A friendly, <b>unique</b> name for the analyzer."),
    )
    notes = models.TextField(blank=True, default="")
    schedule = ArrayField(
        models.CharField(max_length=50),
        default=list,
        null=True,
        blank=True,
        verbose_name="Array of crontab schedule patterns that an analyzer can use to determine whether to run.",
    )
    subject_group = TenantForeignKey(
        to=SubjectGroup,
        on_delete=models.CASCADE,
        verbose_name=_("Subject Group"),
        help_text=_("This analyzer applies to subjects in this Subject Group."),
    )

    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this analyzer is active. Set this False instead of deleting this record."),
    )

    search_time_hours = models.FloatField(
        null=False,
        default=24.0,
        verbose_name="Analysis time frame (hours)",
        help_text=_("Analysis will be performed on recent data within this time frame."),
    )
    additional = models.JSONField(blank=True, default=dict)
    quiet_period = models.DurationField(
        null=True,
        blank=True,
        verbose_name="Quiet period (HH:MM:SS)",
        help_text=_("This will be used to override the configured quiet period."),
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"

    class Meta:
        abstract = True
        app_label = "analyzers"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"])]
        base_manager_name = "objects"
        default_manager_name = "objects"

    analyzer_category = "generic"


class SubjectAnalyzerResult(TenantModelMixin, TimestampedModel):
    LEVEL_OK = OK

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    analyzer_revision = models.IntegerField(default=1)
    subject = TenantForeignKey(Subject, on_delete=models.CASCADE)
    geometry_collection = models.GeometryCollectionField()
    estimated_time = models.DateTimeField()
    level = models.IntegerField()
    observations = models.ManyToManyField(
        Observation,
        related_name="+",
        through="analyzers.SubjectAnalyzerResultObservations",
        through_fields=(
            "subjectanalyzerresult",
            "observation",
        ),
    )
    values = models.JSONField(default=dict, blank=True)
    title = models.TextField(default="", blank=True)
    message = models.TextField(default="", blank=True)

    # TODO: Reference GeoFeature table, and FileContent (which will soon exist as models).
    # geometries = models.ForeignKey('GeoFeature', on_delete=models.PROTECT)
    # images

    # Remaining attributes are to reference the analyzer that created me.
    limits = (
        models.Q(app_label="analyzers", model="immobilityanalyzer")
        | models.Q(app_label="analyzers", model="geofenceanalyzer")
        | models.Q(app_label="analyzers", model="environmentalanalyzer")
    )

    subject_analyzer_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=limits)
    subject_analyzer_id = models.UUIDField()
    subject_analyzer = GenericForeignKey("subject_analyzer_content_type", "subject_analyzer_id")
    subject_analyzer_revision = models.PositiveIntegerField(default=1)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        indexes = [Index(fields=["subject_analyzer_id", "subject"])]

    def __str__(self):
        _tmp_str = (
            f"Subject: {self.subject.name}, Values: {str(self.values)}, Title: {str(self.title)}, "
            f"Est.Time: {str(self.estimated_time)}, Geometry: {str(self.geometry_collection)}"
        )

        return _tmp_str


class SubjectAnalyzerResultObservations(TenantThroughModel):
    subjectanalyzerresult = TenantForeignKey("analyzers.SubjectAnalyzerResult", on_delete=models.CASCADE)
    observation = TenantForeignKey("observations.Observation", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "subjectanalyzerresult", "observation"],
                name="%(app_label)s_%(class)s_tenant_from_to_unique",
            ),
        ]


class Annotator(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = TenantForeignKey(to=Subject, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    @property
    def name(self):
        return self.__class__.__name__

    def annotate(self, subject):
        logger.info("%s annotating subject: %s", self.name, subject.name)

    class Meta:
        abstract = True
        app_label = "analyzers"
        base_manager_name = "objects"
        default_manager_name = "objects"
