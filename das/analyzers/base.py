import logging
from typing import Optional

from django.core.cache import cache

from analyzers.models import SubjectAnalyzerResult
from observations.models import Subject

logger = logging.getLogger(__name__)
"""
Base objects for Analyzer code.
"""


class SubjectAnalyzer:

    def __init__(self, subject=None, config=None):
        self.config = config
        # If subject is not None and if it is inactive subject(is_active=False)
        # Throw ValueError
        if subject and not subject.is_active:
            raise ValueError("Error while initializing analyzer," " {} subject is not active".format(subject.name))
        self.subject = subject

    def analyze_trajectory(self, traj=None):
        raise NotImplementedError()

    def save_analyzer_result(self, last_result=None, this_result=None):
        raise NotImplementedError()

    def create_analyzer_event(self, last_result=None, this_result=None):
        raise NotImplementedError()

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        raise NotImplementedError()

    def get_last_result(self):
        try:
            last_result = SubjectAnalyzerResult.objects.filter(
                subject=self.subject, subject_analyzer_id=self.config.id
            ).latest("estimated_time")
        except SubjectAnalyzerResult.DoesNotExist:
            last_result = None

        return last_result

    def analyze(self, observations=None, trajectory_filter=None, analyzer_key=None):

        # Get default observations list if one isn't provided
        observations = observations or self.default_observations()

        # Use default trajectory_filter if one isn't provided
        trajectory_filter = trajectory_filter or self.subject.default_trajectory_filter()

        # Create Trajectory which is the input to the analysis.
        trajectory = self.subject.create_trajectory(obs=observations, trajectory_filter_params=trajectory_filter)

        results = self.analyze_trajectory(trajectory)

        analyze_results = []

        for this_result in results:

            # Get the last analyzer result
            last_result = self.get_last_result()

            if not self._is_within_feature_group_filter(this_result):
                continue

            # Save the current result in the context of the last result saved
            self.save_analyzer_result(last_result=last_result, this_result=this_result)

            this_event = self.create_analyzer_event(last_result=last_result, this_result=this_result)
            if analyzer_key and this_event:
                logger.info("Pausing analyzer with id=%s", self.config.id)
                cache.set(analyzer_key, analyzer_key, self.config.quiet_period.total_seconds())

            if this_event is not None and this_result.pk:
                SubjectAnalyzerResult.objects.filter(pk=this_result.pk).update(event=this_event)
                this_result.event = this_event

            analyze_results.append((this_result, this_event))

        return analyze_results

    def _is_within_feature_group_filter(self, result) -> bool:
        """Return True if the result's location falls within the configured feature group filter.

        If no feature_group_filter is configured, always returns True.
        """
        if not self.config.feature_group_filter:
            return True
        if not result.geometry_collection:
            logger.warning("Result has empty geometry_collection, skipping feature group filter check")
            return False
        location = result.geometry_collection[0]
        return self._is_location_in_cached_features(location)

    def _is_location_in_cached_features(self, location) -> bool:
        """Check if location intersects with cached feature group geometries.

        Note: Geometries are cached for 1 hour. Changes to the spatial features
        in the feature group (add/remove/edit) will not take effect until the
        cache entry expires.
        """
        cache_key = f"feature_group_{self.config.feature_group_filter.id}_geometries"
        geometries = cache.get(cache_key)

        if geometries is None:
            geometries = list(self.config.feature_group_filter.features.values_list("feature_geometry", flat=True))
            cache.set(cache_key, geometries, 3600)  # Cache for 1 hour

        return any(location.intersects(geom) for geom in geometries)

    def _get_analyzer_key(self, subject: Subject) -> Optional[str]:
        if self.config.quiet_period:
            return f"analyzer_silent__{self.config.id}__{subject.id}"
        return None

    class Meta:
        abstract = True
        app_label = "subject_analyzer"
