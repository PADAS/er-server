from core.models import models, TimestampedModel
from observations.models import Subject
from analyzers.models.base import Schedule
import uuid
from django.contrib.postgres.fields import JSONField
import pymet


class SubjectSpeedProfile(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE, primary_key=True,)


class SpeedDistro(TimestampedModel):
    """
    Represents an empirical speed distribution for a subject for the period within the start until the end
    The distro percentiles/parameters are only valid for the corresponding schedule
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    percentiles = JSONField()
    subject_speed_profile = models.ForeignKey(to=SubjectSpeedProfile,
                                              on_delete=models.CASCADE,
                                              related_name='SpeedDistros')

    # schedules = models.ManyToManyField(to=Schedule, related_name='schedules')

    def update_percentiles(self, percentiles, trajectory_filter=None):

        """ Determine the speed distribution based on the current subject + schedule"""
        obs = self.subject_speed_profile.subject.observations()  # ToDo: use obs from current schedule period only

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject_speed_profile.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject_speed_profile.subject.create_trajectory(obs, trajectory_filter)

        # Calculate the speed percentile value
        speed_percentiles = traj.speed_percentiles(percentiles=percentiles)

        # Copy the percentile speed values from the trajectory object dict
        for p, v in speed_percentiles.iteritems():
            try:
                self.percentiles[p] = v
            except:
                pass

        self.save()
