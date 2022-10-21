import uuid

from django.contrib.postgres.fields import ArrayField

from core.models import TimestampedModel, models
from observations.models import Subject


class SubjectSpeedProfile(TimestampedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    subject = models.OneToOneField(
        to=Subject, on_delete=models.CASCADE, null=True, blank=True)


class SpeedDistro(TimestampedModel):
    """
    Represents an empirical speed distribution for a subject for the period within the start until the end
    The distro percentiles/parameters are only valid for the corresponding schedule
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    percentiles = models.JSONField(blank=True, default=dict)
    subject_speed_profile = models.ForeignKey(to=SubjectSpeedProfile,
                                              on_delete=models.CASCADE,
                                              related_name='SpeedDistros',
                                              null=True, blank=True)

    speeds_kmhr = ArrayField(
        base_field=models.FloatField(), null=True, blank=True)

    # schedule = models.ManyToManyField(to=Schedule)

    def update_percentiles(self, percentiles, trajectory_filter=None, end=None, ignore_zeroes=True):
        """ Determine the speed distribution based on the current subject + schedule"""

        # ToDo: use obs from current schedule period only
        obs = self.subject_speed_profile.subject.observations(until=end)

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject_speed_profile.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject_speed_profile.subject.create_trajectory(
            obs, trajectory_filter)

        # Calculate the speed percentile value
        speed_percentiles = traj.speed_percentiles(
            percentiles=percentiles, ignore_zeroes=ignore_zeroes)

        # Copy the percentile speed values from the trajectory object dict
        for p, v in speed_percentiles.items():
            try:
                self.percentiles[p] = v
            except:
                pass

        self.save()

    def update_speeds_array(self, trajectory_filter=None, end=None, ignore_zeroes=True):
        """ Determine the speed distribution based on the current subject + schedule"""

        # ToDo: use obs from current schedule period only
        obs = self.subject_speed_profile.subject.observations(until=end)

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject_speed_profile.subject.default_trajectory_filter()

        # Create a Trajectory
        traj = self.subject_speed_profile.subject.create_trajectory(
            obs, trajectory_filter)

        speeds = []
        for s in traj.traj_segs:
            if ignore_zeroes is True:
                if s.speed_kmhr > 0.0:
                    speeds.append(s.speed_kmhr)
            else:
                speeds.append(s.speed_kmhr)

        self.speeds_kmhr = speeds

        self.save()
