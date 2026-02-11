import json
import logging
import uuid

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.models import CRITICAL, WARNING
from analyzers.models.base import EVENT_PRIORITY_MAP
from analyzers.utils import save_analyzer_event


class ObservationAttributeAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        SubjectAnalyzer.__init__(self, subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def subject_analyzers(cls, subject, analyzer_class):
        subject_groups = subject.get_ancestor_subject_groups()
        for ac in analyzer_class.objects.filter(subject_group__in=subject_groups, is_active=True):
            yield cls(subject=subject, config=ac)

    def default_observations(self):
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        # observations get passed back in temporally descending order
        if self.config.search_time_hours <= 0:
            return list(self.subject.observations())[:2]
        else:
            return list(self.subject.observations(last_hours=self.config.search_time_hours))[:2]

    def save_analyzer_result(self, last_result=None, this_result=None):

        if this_result is not None:
            # Save if result is critical or warning
            if this_result.level in (CRITICAL, WARNING):
                this_result.save()

    def value_to_display(self, value):
        return " ".join(x.capitalize() or "_" for x in value.split("_"))

    def evaluate_return_value(self, value):
        if not isinstance(value, str):
            value = value[0]

        if isinstance(value, float):
            value = round(value, 2)

        return value

    def verify_event_type(self, this_result):
        from analyzers.subject_proximity import (
            SUBJECT_PROXIMITY_SCHEMA,
            SubjectProximityAnalyzerConfig,
        )

        et_value = this_result.subject_analyzer.analyzer_category
        et_display = self.value_to_display(et_value)
        et_defaults_dict = dict(display=et_display)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )
        et, created = EventType.objects.get_or_create(value=et_value, category=ec, defaults=et_defaults_dict)

        if created and isinstance(this_result.subject_analyzer, SubjectProximityAnalyzerConfig):
            et.schema = json.dumps(SUBJECT_PROXIMITY_SCHEMA, indent=2, default=str)
            et.save()
        return et_value

    def create_analyzer_event(self, last_result=None, this_result=None):

        # no data to create an event so exit
        if not this_result:
            return

        event_data = None

        event_details = {"name": self.subject.name}
        event_details.update(this_result.values)

        # Create a dict() location to satisfy our EventSerializer.
        event_location_value = {
            "longitude": this_result.geometry_collection[0].x,
            "latitude": this_result.geometry_collection[0].y,
        }

        event_type = self.verify_event_type(this_result)
        relate_subjects = [{"id": self.subject.id}]

        if this_result.values.get("subject_2_id"):
            subject_2_id = self.evaluate_return_value(this_result.values.get("subject_2_id"))
            relate_subjects.append({"id": uuid.UUID(subject_2_id)})

        # Notify if result is critical or warning
        if this_result.level in (CRITICAL, WARNING):
            event_data = dict(
                title=this_result.title,
                time=this_result.estimated_time,
                provenance=Event.PC_ANALYZER,
                event_type=event_type,
                priority=EVENT_PRIORITY_MAP.get(this_result.level, Event.PRI_URGENT),
                location=event_location_value,
                event_details=event_details,
                related_subjects=relate_subjects,
            )

        if event_data:
            return save_analyzer_event(event_data)
