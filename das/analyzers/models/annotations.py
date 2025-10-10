import logging
from datetime import datetime, timedelta

import psycopg2.extras
import pytz

from django.conf import settings
from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import Annotator
from observations.models import Observation, SubjectSource
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)

# ObservationAnnotator
DEFAULT_HISTORY_INTERVAL = timedelta(days=7)
try:
    DEFAULT_SPEED_THRESHOLDS = settings.ANNOTATION_SETTINGS["speed_thresholds"]
except (AttributeError, KeyError):
    DEFAULT_SPEED_THRESHOLDS = {}


class ObservationAnnotator(Annotator):
    class Meta(Annotator.Meta):
        verbose_name = _("Subject Track Filter")
        verbose_name_plural = _("Subject Track Filters")

    @classmethod
    def should_run(cls, *args, **kwargs):
        return True

    @classmethod
    def get_for_subject(self, subject):
        if subject.subject_subtype_id in DEFAULT_SPEED_THRESHOLDS:
            # Set the generic default max speed very high, in case this gets
            # executed without values in settings.
            max_speed = DEFAULT_SPEED_THRESHOLDS.get(subject.subject_subtype_id, None)

            # there isn't a unique constraint on the subject_id, so we need to check for existence and possibly multiple existences
            annotator = ObservationAnnotator.objects.filter(subject_id=subject.id).first()
            if not annotator:
                annotator, created = ObservationAnnotator.objects.get_or_create(
                    subject_id=subject.id, defaults={"max_speed": max_speed}
                )
                if created:
                    logger.info(
                        "Created ObseravtionAnnotator for Subject %s with max-speed-threshold: %s", subject, max_speed
                    )

            return annotator

        try:
            return ObservationAnnotator.objects.filter(subject_id=subject.id).first()
        except ObservationAnnotator.DoesNotExist:
            # This is acceptable, since no default is set for this Subject's sub-type.
            pass

    # Maximum speed in kilometers per hour.
    max_speed = models.FloatField(default=10.0, verbose_name="Maximum speed (km/h)")

    def annotate(self, start_date=None, end_date=None):
        end_date = end_date or pytz.utc.localize(datetime.utcnow())
        start_date = start_date or (end_date - DEFAULT_HISTORY_INTERVAL)

        date_range = psycopg2.extras.DateTimeTZRange(lower=start_date, upper=end_date)
        subject_sources = SubjectSource.objects.filter(subject=self.subject, assigned_range__contains=date_range)

        tenant = get_tenant_settings()
        for ss in subject_sources:
            self.annotate_by_subject_source(ss, start_date, end_date, tenant_id=str(tenant.id))

    def annotate_by_subject_source(self, subject_source, start_date, end_date, tenant_id: str):
        """For my first crack at this, I'm going to let speeds be calculated within the database."""
        sql = """
        with path as (select obs.*,
           ST_Distance(obs.location::geography, lag(obs.location::geography, 1) over (order by obs.recorded_at)) as distance_preceding,
           extract('epoch' from age(obs.recorded_at, lag(obs.recorded_at) over (order by obs.recorded_at))) as time_lapse_preceding,
           ST_Distance(obs.location::geography, lead(obs.location::geography, 1) over (order by obs.recorded_at)) as distance_following,
           extract('epoch' from age(lead(obs.recorded_at) over (order by obs.recorded_at), obs.recorded_at)) as time_lapse_following

        from observations_observation obs join observations_subjectsource ss on ss.source_id = obs.source_id and
                                         ss.assigned_range @> obs.recorded_at
          where ss.id = %(subject_source_id)s
             and obs.das_tenant_id=%(tenant_id)s
             and %(start_date)s <= obs.recorded_at and obs.recorded_at <= %(end_date)s
             and obs.location::Point <> ST_GeomFromText('POINT(0 0)', 4326)::Point
             and obs.exclusion_flags = 0
          order by obs.recorded_at asc)

        select id, recorded_at, location::bytea, additional, distance_preceding, time_lapse_preceding, distance_following, time_lapse_following,
             (3.6 * distance_preceding / time_lapse_preceding) kph_preceding,
             (3.6 * distance_following / time_lapse_following) kph_following
           from path
          where (3.6 * distance_preceding / time_lapse_preceding) > %(speed_threshold)s
            and (distance_following is null or (3.6 * distance_following / time_lapse_following) > %(speed_threshold)s)
          order by recorded_at asc;
        """

        items = Observation.objects.raw(
            sql,
            dict(
                subject_source_id=str(subject_source.id),
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                speed_threshold=self.max_speed,
            ),
        )

        flag_these = [item.id for item in items]

        logger.info("Setting exclusion_flags on these observations: {}".format(flag_these))
        Observation.objects.set_flag(flag_these, Observation.EXCLUDED_AUTOMATICALLY)

    def annotate_queryset(self, queryset):
        """
        Annotate a queryset with distance, time, and speed calculations.

        This method adds the proven SQL logic for calculating distances and speeds
        between consecutive observations, which can be reused by other components.

        Returns queryset with additional fields:
        - distance_preceding: Distance from previous observation (meters)
        - time_lapse_preceding: Time gap from previous observation (seconds)
        - speed_kmh: Speed in km/h based on distance and time

        Note: This is a simplified version that works with Django ORM limitations.
        For production use, consider using the more complex raw SQL approach.
        """
        # constrain complexity to maintain compatibility with
        #  Django's limitations around .extra().
        # be careful with table aliases and references.

        return queryset.extra(
            select={
                "distance_preceding": """
                    ST_Distance(
                        "observations_observation"."location"::geography,
                        lag("observations_observation"."location"::geography, 1) OVER (
                            PARTITION BY "observations_observation"."source_id"
                            ORDER BY "observations_observation"."recorded_at"
                        )
                    )
                """,
                "time_lapse_preceding": """
                    extract('epoch' FROM age(
                        "observations_observation"."recorded_at",
                        lag("observations_observation"."recorded_at") OVER (
                            PARTITION BY "observations_observation"."source_id"
                            ORDER BY "observations_observation"."recorded_at"
                        )
                    ))
                """,
                "speed_kmh": """
                    CASE WHEN extract('epoch' FROM age(
                        "observations_observation"."recorded_at",
                        lag("observations_observation"."recorded_at") OVER (
                            PARTITION BY "observations_observation"."source_id"
                            ORDER BY "observations_observation"."recorded_at"
                        )
                    )) > 0
                    THEN (3.6 *
                        ST_Distance(
                            "observations_observation"."location"::geography,
                            lag("observations_observation"."location"::geography, 1) OVER (
                                PARTITION BY "observations_observation"."source_id"
                                ORDER BY "observations_observation"."recorded_at"
                            )
                        ) /
                        extract('epoch' FROM age(
                            "observations_observation"."recorded_at",
                            lag("observations_observation"."recorded_at") OVER (
                                PARTITION BY "observations_observation"."source_id"
                                ORDER BY "observations_observation"."recorded_at"
                            )
                        ))
                    )
                    ELSE 0 END
                """,
            }
        )

    def annotate_with_segmentation(self, queryset, max_time_gap_hours=24.0, speed_threshold_kmh=None):
        """
        PRODUCTION-READY: Annotate queryset with track segmentation using optimized raw SQL.

        This method uses a CTE-based approach for optimal performance with large datasets.

        Args:
            queryset: Base queryset to annotate
            max_time_gap_hours: Maximum hours between observations before breaking track
            speed_threshold_kmh: Speed threshold for breaking tracks (uses self.max_speed if None)

        Returns queryset with additional fields:
        - distance_preceding, time_lapse_preceding, speed_kmh
        - is_segment_break: Boolean indicating if this observation starts a new segment
        - track_segment_id: Cumulative segment ID within each subject
        - segment_order: Order of observation within its segment
        """
        # Use instance's max_speed if no threshold provided
        if speed_threshold_kmh is None:
            speed_threshold_kmh = self.max_speed

        # Get observation IDs from the queryset
        observation_ids = list(queryset.values_list("id", flat=True))

        if not observation_ids:
            return queryset.none()

        # Production-ready raw SQL with CTE for optimal performance
        sql = """
        WITH track_analysis AS (
            SELECT
                obs.*,
                ss.subject_id,
                ST_Distance(
                    obs.location::geography,
                    lag(obs.location::geography) OVER (
                        PARTITION BY ss.subject_id
                        ORDER BY obs.recorded_at
                    )
                ) as distance_preceding,
                extract('epoch' FROM age(
                    obs.recorded_at,
                    lag(obs.recorded_at) OVER (
                        PARTITION BY ss.subject_id
                        ORDER BY obs.recorded_at
                    )
                )) as time_lapse_preceding
            FROM observations_observation obs
            JOIN observations_source s ON s.id = obs.source_id
            JOIN observations_subjectsource ss ON ss.source_id = s.id
                AND ss.assigned_range @> obs.recorded_at
            WHERE obs.id IN %s
        ),
        track_segments AS (
            SELECT
                *,
                CASE WHEN time_lapse_preceding > 0
                    THEN (3.6 * distance_preceding / time_lapse_preceding)
                    ELSE 0
                END as speed_kmh,
                CASE
                    WHEN lag(recorded_at) OVER (
                        PARTITION BY subject_id ORDER BY recorded_at
                    ) IS NULL THEN 1
                    WHEN time_lapse_preceding > %s THEN 1
                    WHEN time_lapse_preceding > 0
                        AND (3.6 * distance_preceding / time_lapse_preceding) > %s THEN 1
                    ELSE 0
                END as is_segment_break
            FROM track_analysis
        ),
        final_segments AS (
            SELECT
                *,
                SUM(is_segment_break) OVER (
                    PARTITION BY subject_id
                    ORDER BY recorded_at
                    ROWS UNBOUNDED PRECEDING
                ) - 1 as track_segment_id
            FROM track_segments
        )
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY subject_id, track_segment_id
                ORDER BY recorded_at
            ) as segment_order
        FROM final_segments
        ORDER BY subject_id, recorded_at
        """

        # Use proper parameterization to avoid SQL injection
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(sql, [observation_ids, max_time_gap_hours * 3600, speed_threshold_kmh])

            # Convert results to Observation instances
            columns = [col[0] for col in cursor.description]
            results = []

            for row in cursor.fetchall():
                observation = Observation()
                # Set all fields from the row
                for i, value in enumerate(row):
                    setattr(observation, columns[i], value)
                results.append(observation)

            return results
