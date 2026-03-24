import json
import logging
import statistics
from typing import Any, Optional

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.core.cache import cache

from activity.models import Event, EventCategory, EventType
from analyzers.base import SubjectAnalyzer
from analyzers.models import ObservationAttributeAnalyzerConfig, SubjectAnalyzerResult
from analyzers.models.base import CRITICAL, EVENT_PRIORITY_MAP, WARNING
from analyzers.utils import save_analyzer_event
from observations.models import Observation

logger = logging.getLogger(__name__)


class ObservationAttributeAnalyzer(SubjectAnalyzer):

    def __init__(self, subject=None, config=None):
        super().__init__(subject=subject, config=config)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def get_subject_analyzers(cls, subject=None):
        if subject:
            subject_groups = subject.get_ancestor_subject_groups()
            for ac in ObservationAttributeAnalyzerConfig.objects.select_related("feature_group_filter").filter(
                subject_group__in=subject_groups, is_active=True
            ):
                yield cls(subject=subject, config=ac)

    def default_observations(self) -> list[Observation]:
        """
        Default set of observation is fetched from the database, based on this analyzer's configuration.
        :return: a queryset of Observations
        """
        return list(self.subject.observations(last_hours=self.config.search_time_hours or 24))

    def save_analyzer_result(self, last_result=None, this_result=None) -> None:
        if this_result is not None:
            this_result.save()

    def value_to_display(self, value) -> str:
        return " ".join(x.capitalize() or "_" for x in value.split("_"))

    def verify_event_type(self, this_result: SubjectAnalyzerResult) -> str:
        """Ensures that a target event type for this analyzer exists and, if it doesn't, creates one.

        Args:
            this_result (SubjectAnalyzerConfig.Result): The result object to verify event type for.

        Returns:
            _type_: The value of the event type associated with this analyzer result.
        """

        et_value = this_result.subject_analyzer.analyzer_category
        et_display = self.value_to_display(et_value)
        et_defaults_dict = dict(display=et_display)

        ec, created = EventCategory.objects.get_or_create(
            value="analyzer_event", defaults=dict(display="Analyzer Events")
        )
        et, created = EventType.objects.get_or_create(value=et_value, category=ec, defaults=et_defaults_dict)

        if created and isinstance(this_result.subject_analyzer, ObservationAttributeAnalyzerConfig):
            et.schema = json.dumps(OBSERVATION_ATTRIBUTE_ANALYZER_SCHEMA, indent=2, default=str)
            et.save()
        return et_value

    @staticmethod
    def _aggregate(value_list: list, aggregation_function: str) -> Optional[float]:
        """

        Aggregates a list of values based on the specified aggregation function.

        Args:
            value_list (list): A list of values to aggregate.
            aggregation_function (str): The aggregation function to apply. Supported values are "mean", "median", "min",
                                        "max", "range", and "stdev".

        Returns:
            Optional[float]: The aggregated value, or None if aggregation fails.
        """
        try:
            if aggregation_function == "mean":
                return statistics.mean(value_list)
            elif aggregation_function == "median":
                return statistics.median(value_list)
            elif aggregation_function == "min":
                return min(value_list)
            elif aggregation_function == "max":
                return max(value_list)
            elif aggregation_function == "range":
                return max(value_list) - min(value_list)
            elif aggregation_function == "stdev":
                return statistics.stdev(value_list)
        except TypeError:
            return None

        return None

    @staticmethod
    def _compare_value(value: Any, comparator: str, target_value: Any) -> bool:
        """
        Compares a value to a comparison value using the specified comparator.

        Args:
            value (Any): The value to compare.
            comparator (str): The comparator to use. Supported values are "<", ">", "=", "<=", ">=", and "<>".
            target_value (Any): The value to compare against.

        Returns:
            bool: True if the comparison is satisfied, False otherwise.
        """
        try:
            if comparator == "<":
                return value < target_value
            elif comparator == ">":
                return value > target_value
            elif comparator == "=":
                return value == target_value
            elif comparator == "<=":
                return value <= target_value
            elif comparator == ">=":
                return value >= target_value
            elif comparator == "<>":
                return value != target_value

        except TypeError:
            return False

        return False

    def create_analyzer_event(self, last_result=None, this_result=None) -> Optional[Event]:
        """
        Creates an EarthRanger event based on the analyzer result.

        Args:
            last_result (_type_, optional): The previous analyzer result. This is not used in the current implementation
                                            but is required by the parent class.  Defaults to None.
            this_result (_type_, optional): The current analyzer result. Defaults to None.

        Returns:
            _type_: The created event object, or None if no event was created.
        """

        if not this_result:
            return

        event_data = dict(
            title=this_result.title,
            priority=this_result.level or Event.PRI_URGENT,
            time=this_result.estimated_time,
            provenance=Event.PC_ANALYZER,
            event_type=self.verify_event_type(this_result),
            location={
                "longitude": this_result.geometry_collection[0].x,
                "latitude": this_result.geometry_collection[0].y,
            },
            event_details=this_result.values,
            related_subjects=[{"id": self.subject.id}],
        )
        return save_analyzer_event(event_data)

    def _evaluate_rule(self, value_list: list, target_value: Any) -> tuple[bool, Any]:
        """
        Evaluates the analyzer rule against a list of values and determines whether the rule is triggered.

        Args:
            value_list (list): The list of values to evaluate.
            target_value (Any): The target value to compare against.

        Returns:
            tuple: A tuple containing a boolean indicating whether the rule was triggered and the evaluated value.
        """

        oom = self.config.adjust_to_order_of_magnitude or 0
        if oom > 0:
            adjusted_list = []
            for o_val in value_list:
                # To avoid an infinite loop, only adjust if the value is greater than 0
                if o_val > 0:
                    while o_val < oom:
                        o_val = o_val * 10
                adjusted_list.append(o_val)
            value_list = adjusted_list

        evaluated_value = None
        if self.config.aggregation in ["any", "none", "all"]:
            for o_val in value_list:
                evaluated_value = self._compare_value(o_val, self.config.comparator, target_value)
                if self.config.aggregation == "any" and evaluated_value:
                    return True, target_value

                elif self.config.aggregation == "none" and evaluated_value:
                    return False, None

                elif self.config.aggregation == "all" and not evaluated_value:
                    return False, None

            if self.config.aggregation == "all" or self.config.aggregation == "none":
                return True, target_value
        else:
            evaluated_value = self._aggregate(value_list, self.config.aggregation)
            if evaluated_value is not None and self._compare_value(
                evaluated_value, self.config.comparator, target_value
            ):
                return True, evaluated_value

        return False, None

    def analyze(
        self, observations=None, trajectory_filter=None, analyzer_key=None
    ) -> list[tuple[SubjectAnalyzerResult, Event]]:
        """

        Overrides the parent class because this analyzer doesn't analyze a trajectory but rather a set of observations.
        Analyzes a subject's observations based on this analyzer's configuration and creates an event if the analysis
        triggers.

        Args:
            observations (list, optional): The list of observations to analyze. Defaults to None.
            trajectory_filter (None, optional): Not used. Included to match parent class signature. Defaults to None.
            analyzer_key (str, optional): The analyzer key to use for evaluating the silent period. Defaults to None.

        Returns:
            list[tuple[SubjectAnalyzerResult, Event]]: A list of tuples containing the analyzer result and resulting ER
            event if triggered, otherwise None.
        """

        observations = observations or self.default_observations()
        value_list = []
        for o in observations:
            if self.config.attribute_name in o.additional:
                value_list.append(o.additional.get(self.config.attribute_name))

        if not value_list:
            return []

        triggered, evaluated_value = self._evaluate_rule(value_list, self.config.critical_value)
        level = EVENT_PRIORITY_MAP.get(CRITICAL)

        if not triggered:
            triggered, evaluated_value = self._evaluate_rule(value_list, self.config.warning_value)

            if not triggered:
                return []

            level = EVENT_PRIORITY_MAP.get(WARNING)

        if triggered:

            if isinstance(evaluated_value, float):
                evaluated_value = round(evaluated_value, 2)

            this_result = SubjectAnalyzerResult(
                subject_analyzer=self.config,
                subject=self.subject,
                level=level,
                title=f"{self.subject.name} triggered {self.config.name}",
                estimated_time=observations[-1].recorded_at if observations else None,
                values={
                    "subject_name": self.subject.name,
                    "attribute": self.config.attribute_name,
                    "comparator": self.config.comparator,
                    "warning_value": self.config.warning_value,
                    "critical_value": self.config.critical_value,
                    "evaluated_value": evaluated_value,
                    "total_fix_count": len(observations),
                },
                geometry_collection=DjangoGeoColl(
                    [
                        DjangoPoint(
                            observations[-1].location.x if observations else 0,
                            observations[-1].location.y if observations else 0,
                        )
                    ]
                ),
            )

            self.save_analyzer_result(this_result=this_result)
            this_event = self.create_analyzer_event(this_result=this_result)

            if analyzer_key and this_event and self.config.quiet_period:
                logger.info("Pausing analyzer with id=%s", self.config.id)
                cache.set(analyzer_key, analyzer_key, self.config.quiet_period.total_seconds())

            return [(this_result, this_event)]


OBSERVATION_ATTRIBUTE_ANALYZER_SCHEMA = {
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Observation Attribute Analyzer Schema",
        "type": "object",
        "properties": {
            "subject_name": {"type": "string", "title": "Subject Name"},
            "attribute": {"type": "string", "title": "Attribute"},
            "comparator": {"type": "string", "title": "Comparator"},
            "warning_value": {"type": "number", "title": "Warning Value"},
            "critical_value": {"type": "number", "title": "Critical Value"},
            "evaluated_value": {"type": "number", "title": "Evaluated Value"},
            "total_fix_count": {"type": "number", "title": "Total Fix Count"},
        },
    },
    "definition": [
        {"type": "fieldset", "title": "Analyzer Details", "htmlClass": "col-lg-12", "items": []},
        {
            "type": "fieldset",
            "htmlClass": "col-lg-6",
            "items": [
                "subject_name",
                "attribute",
                "comparator",
                "warning_value",
                "critical_value",
                "evaluated_value",
                "total_fix_count",
            ],
        },
    ],
}
