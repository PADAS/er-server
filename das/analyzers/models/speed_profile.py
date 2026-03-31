import logging
import uuid

from django_multitenant.fields import TenantForeignKey, TenantOneToOneField
from django_multitenant.mixins import TenantModelMixin

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import DASTenant, TimestampedModel
from observations.models import Subject
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager

logger = logging.getLogger(__name__)

# 365 days of history for building baseline speed distributions. A full year
# captures seasonal movement variation (e.g. migration, wet/dry season behaviour)
# which shorter windows would miss. The 30-day comparison window used by
# LowSpeedWilcoxAnalyzer._normal_movement_distro is measured against this baseline.
#
# TODO: Pulling a year of observations every time we recalculate a speed profile is
# expensive for high-frequency trackers (e.g. 15-min fix intervals yield ~35k rows).
# Consider an incremental approach: persist the last-computed timestamp and only
# fetch new observations since then, appending to the existing speeds_kmhr array
# and recomputing percentiles in place. That would reduce the per-run query cost
# from O(year) to O(since_last_run) while keeping the full-year baseline intact.
SPEED_PROFILE_DEFAULT_HOURS = 365 * 24


class SubjectSpeedProfile(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = TenantOneToOneField(to=Subject, on_delete=models.CASCADE, null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()

    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"


class SpeedDistro(TenantModelMixin, TimestampedModel):
    """
    Represents an empirical speed distribution for a subject for the period within the start until the end
    The distro percentiles/parameters are only valid for the corresponding schedule
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    percentiles = models.JSONField(blank=True, default=dict)
    subject_speed_profile = TenantForeignKey(
        to=SubjectSpeedProfile,
        on_delete=models.CASCADE,
        related_name="SpeedDistros",
        null=True,
        blank=True,
    )
    speeds_kmhr = ArrayField(base_field=models.FloatField(), null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = CommonTenantManager()

    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def update_percentiles(self, percentiles, trajectory_filter=None, end=None, ignore_zeroes=True):
        """Determine the speed distribution based on the current subject + schedule"""

        obs = self.subject_speed_profile.subject.observations(last_hours=SPEED_PROFILE_DEFAULT_HOURS, until=end)

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject_speed_profile.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject_speed_profile.subject.create_trajectory(obs, trajectory_filter)

        # Calculate the speed percentile value
        speed_percentiles = traj.speed_percentiles(percentiles=percentiles, ignore_zeroes=ignore_zeroes)

        # Copy the percentile speed values from the trajectory object dict
        for p, v in speed_percentiles.items():
            try:
                self.percentiles[p] = v
            except:
                pass

        self.save()

    def update_speeds_array(self, trajectory_filter=None, end=None, ignore_zeroes=True):
        """Determine the speed distribution based on the current subject + schedule"""

        obs = self.subject_speed_profile.subject.observations(last_hours=SPEED_PROFILE_DEFAULT_HOURS, until=end)

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject_speed_profile.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject_speed_profile.subject.create_trajectory(obs, trajectory_filter)

        speeds = []
        for s in traj.traj_segs:
            if ignore_zeroes is True:
                if s.speed_kmhr > 0.0:
                    speeds.append(s.speed_kmhr)
            else:
                speeds.append(s.speed_kmhr)

        self.speeds_kmhr = speeds

        self.save()
