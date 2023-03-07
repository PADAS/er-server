import logging
from datetime import datetime, timedelta

import psycopg2.extras
import pytz

from django.conf import settings
from django.contrib.gis.db import models
from django.utils.translation import gettext as _

from analyzers.models.base import Annotator
from observations.models import Observation, SubjectSource

logger = logging.getLogger(__name__)

# ObservationAnnotator
DEFAULT_HISTORY_INTERVAL = timedelta(days=7)
try:
    DEFAULT_SPEED_THRESHOLDS = settings.ANNOTATION_SETTINGS['speed_thresholds']
except (AttributeError, KeyError):
    DEFAULT_SPEED_THRESHOLDS = {}


class ObservationAnnotator(Annotator):

    class Meta(Annotator.Meta):
        verbose_name = _('Subject Track Filter')
        verbose_name_plural = _('Subject Track Filters')

    @classmethod
    def should_run(cls, *args, **kwargs):
        return True

    @classmethod
    def get_for_subject(self, subject):

        if subject.subject_subtype_id in DEFAULT_SPEED_THRESHOLDS:
            # Set the generic default max speed very high, in case this gets
            # executed without values in settings.
            max_speed = DEFAULT_SPEED_THRESHOLDS.get(
                subject.subject_subtype_id, None)

            annotator, created = ObservationAnnotator.objects.get_or_create(subject_id=subject.id,
                                                                            defaults={'max_speed': max_speed})
            if created:
                logger.info(
                    'Created ObseravtionAnnotator for Subject %s with max-speed-threshold: %s', subject, max_speed)

            return annotator

        try:
            return ObservationAnnotator.objects.get(subject_id=subject.id)
        except ObservationAnnotator.DoesNotExist:
            # This is acceptable, since no default is set for this Subject's sub-type.
            pass

    # Maximum speed in kilometers per hour.
    max_speed = models.FloatField(
        default=10.0, verbose_name='Maximum speed (km/h)')

    def annotate(self, start_date=None, end_date=None):
        end_date = end_date or pytz.utc.localize(datetime.utcnow())
        start_date = start_date or (end_date - DEFAULT_HISTORY_INTERVAL)

        date_range = psycopg2.extras.DateTimeTZRange(
            lower=start_date, upper=end_date)
        subject_sources = SubjectSource.objects.filter(
            subject=self.subject, assigned_range__contains=date_range)

        for ss in subject_sources:
            self.annotate_by_subject_source(ss, start_date, end_date)

    def annotate_by_subject_source(self, subject_source, start_date, end_date):
        '''For my first crack at this, I'm going to let speeds be calculated within the database.'''
        sql = '''
        with path as (select obs.*,
           ST_Distance(obs.location::geography, lag(obs.location::geography, 1) over (order by obs.recorded_at)) as distance_preceding,
           extract('epoch' from age(obs.recorded_at, lag(obs.recorded_at) over (order by obs.recorded_at))) as time_lapse_preceding,
           ST_Distance(obs.location::geography, lead(obs.location::geography, 1) over (order by obs.recorded_at)) as distance_following,
           extract('epoch' from age(lead(obs.recorded_at) over (order by obs.recorded_at), obs.recorded_at)) as time_lapse_following

        from observations_observation obs join observations_subjectsource ss on ss.source_id = obs.source_id and
                                         ss.assigned_range @> obs.recorded_at
          where ss.id = %(subject_source_id)s
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
        '''

        items = Observation.objects.raw(sql, dict(subject_source_id=str(subject_source.id), start_date=start_date,
                                                  end_date=end_date, speed_threshold=self.max_speed))

        flag_these = [item.id for item in items]

        logger.info(
            'Setting exclusion_flags on these observations: {}'.format(flag_these))
        Observation.objects.set_flag(
            flag_these, Observation.EXCLUDED_AUTOMATICALLY)
