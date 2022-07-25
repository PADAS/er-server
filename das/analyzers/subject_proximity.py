import datetime as dt
import math

import pymet
from pymet.proximity import ProximityAnalysisResult

from django.contrib.gis.geos import GeometryCollection as DjangoGeoColl
from django.contrib.gis.geos import Point as DjangoPoint
from django.utils.translation import gettext_lazy as _

from analyzers.models import (CRITICAL, SubjectAnalyzerResult,
                              SubjectProximityAnalyzerConfig)
from analyzers.proximity import ProximityAnalyzer


class SubjectProximityAnalyzer(ProximityAnalyzer):

    @classmethod
    def get_subject_analyzers(cls, subject):
        return cls.subject_analyzers(subject, SubjectProximityAnalyzerConfig)

    def _create_proximity_analysis_params(self, analysis_subject):
        second_group_subjects = self.config.second_subject_group.subjects.all()
        if analysis_subject in second_group_subjects:
            second_group_subjects = second_group_subjects.exclude(
                name=analysis_subject.name)
        return [k for k in second_group_subjects]

    def default_observations(self):
        if self.config.analysis_search_time_hours <= 0:
            return list(self.subject.observations())
        else:
            return list(self.subject.observations(last_hours=self.config.analysis_search_time_hours))

    def analyze_trajectory(self, traj=None):
        """
        A function to analyze the trajectory of a subject in relation to a set of other subjects to
        determine where/when the subject was proximal to the other subject
        """

        if traj is None:
            return

        analysis_params = self._create_proximity_analysis_params(self.subject)

        # Subsample trajectory to the last two fixes
        traj = pymet.base.Trajectory(relocs=pymet.base.Relocations(fixes=traj.relocs.get_fixes()[-2:],
                                                                   subject_id=self.subject.id))

        proximity_results = SubjectProximityAnalysis.calc_proximity_events(
            self.subject,
            self.config,
            proximity_analysis_params=analysis_params,
            trajectories=[traj],
        )

        das_analyzer_results = []
        for prox in proximity_results.proximity_events:
            # Create a DAS Analyser result based on each proximity event within
            if prox.proximity_distance_meters <= self.config.threshold_dist_meters:

                subject_2_name = self.evaluate_return_value(
                    prox.subject_2_name) if prox.subject_2_name else ''

                # Create the analyzer result
                result = SubjectAnalyzerResult(subject_analyzer=self.config,
                                               title=self.subject.name + str(_(' is near ')) +
                                               subject_2_name + '.',
                                               level=CRITICAL,
                                               message=self.subject.name + str(_(' is near ')) +
                                               subject_2_name + '.',
                                               analyzer_revision=1,
                                               subject=self.subject)

                # Define the latest fix as the estimated time
                result.estimated_time = prox.proximal_fix.fixtime

                # Define the geometry to be the latest fix geometry
                result.geometry_collection = DjangoGeoColl(
                    [DjangoPoint(prox.proximal_fix.geopoint.ogr_geometry.GetX(),
                                 prox.proximal_fix.geopoint.ogr_geometry.GetY())])

                result.values = {
                    'subject_1_id': prox.subject_1_id,
                    'subject_1_name': self.evaluate_return_value(prox.subject_1_name),
                    'subject_1_speed_kmhr': self.evaluate_return_value(prox.subject_1_speed),
                    'subject_1_heading': self.evaluate_return_value(prox.subject_1_travel_heading),
                    'subject_1_location': prox.subject_1_location[0],

                    'subject_2_id': prox.subject_2_id,
                    'subject_2_name': self.evaluate_return_value(prox.subject_2_name),
                    'subject_2_speed_kmhr': self.evaluate_return_value(prox.subject_2_speed),
                    'subject_2_heading': self.evaluate_return_value(prox.subject_2_travel_heading),
                    'subject_2_location': prox.subject_2_location[0],

                    'proximity_dist_meters': prox.proximity_distance_meters,
                    'total_fix_count': traj.relocs.fix_count
                }

                self.logger.info(result.message)

                das_analyzer_results.append(result)
        return das_analyzer_results


class SubjectProximityAnalysis:

    @classmethod
    def get_subject_latest_obs(cls, subject):
        if subject.observations:
            obs = subject.observations().latest('recorded_at')
            return obs

    @classmethod
    def verify_proximal_tracks_time_frame(cls, config, latest_observation_analysis_subject, latest_observation_second_subject):
        if latest_observation_analysis_subject and latest_observation_second_subject and \
                abs(latest_observation_analysis_subject.recorded_at - latest_observation_second_subject.recorded_at).total_seconds() <= config.proximity_time * 3600:
            return True

    @classmethod
    def calc_proximity_events(cls, analysis_subject, config, proximity_analysis_params=None, trajectories=None):
        """
        :param analysis_subject:
        :param configuration:
        :param proximity_analysis_params:
        :param trajectories:
        :return:
        """

        trajectories = trajectories or []

        # Create the output analysis result object
        result = ProximityAnalysisResult()

        # Set the start time of the analysis
        result.analysis_start = dt.datetime.utcnow()
        latest_observation_analysis_subject = cls.get_subject_latest_obs(
            analysis_subject)

        for traj in trajectories:
            assert type(traj) is pymet.base.Trajectory

            for seg in traj.traj_segs:
                for subject in proximity_analysis_params:
                    # create_trajectory
                    subject_traj = subject.create_trajectory(
                        trajectory_filter_params=subject.default_trajectory_filter())

                    # Subsample trajectory to the last two fixes
                    subject_trajectories = pymet.base.Trajectory(
                        relocs=pymet.base.Relocations(
                            fixes=subject_traj.relocs.get_fixes()[-2:], subject_id=subject.id))

                    for subject_traj in [subject_trajectories]:
                        for seg2 in subject_traj.traj_segs:

                            latest_observation_second_subject = cls.get_subject_latest_obs(
                                subject)
                            valid_proximal_time = cls.verify_proximal_tracks_time_frame(
                                config, latest_observation_analysis_subject, latest_observation_second_subject)

                            if valid_proximal_time:
                                # # Calculate the distance between the two subject
                                proximity_dist = seg.end_fix_geopoint.dist_to_point(
                                    seg2.end_fix_geopoint.ogr_geometry)

                                # Create the proximity event
                                prox_event = SubjectProximityEvent(
                                    subject_1_id=str(analysis_subject.id),
                                    subject_1_name=analysis_subject.name,
                                    subject_1_speed=round(seg.speed_kmhr, 2),
                                    subject_1_location=cls.get_map_coords(
                                        latest_observation_analysis_subject),

                                    subject_2_id=str(subject.id),
                                    subject_2_name=subject.name,
                                    subject_2_speed=round(seg2.speed_kmhr, 2),
                                    subject_2_location=cls.get_map_coords(
                                        latest_observation_second_subject),

                                    subject_1_travel_heading=round(
                                        seg.heading, 2),
                                    subject_2_travel_heading=round(
                                        seg2.heading, 2),
                                    proximal_fix=seg.end_fix,
                                    proximity_distance_meters=proximity_dist
                                )
                                # Add this given crossing to the result
                                result.add_proximity_event(prox_event)

        # Set the end time of the analysis
        result.analysis_end = dt.datetime.utcnow()

        return result

    @classmethod
    def get_map_coords(cls, track):
        if track.location:
            location = track.location.coords  # lon/lat
            return ', '.join(map(str, location[::-1]))  # lat/lon


class SubjectProximityEvent:

    """ Class to store the result of a single proximity event"""

    def __init__(self, subject_1_id, subject_1_name, subject_1_speed, subject_1_location,
                 subject_2_id, subject_2_name, subject_2_speed, subject_2_location,
                 subject_1_travel_heading=0.0, subject_2_travel_heading=0.0,
                 proximal_fix=None, proximity_distance_meters=math.inf):

        self.subject_1_id = subject_1_id,
        self.subject_1_name = subject_1_name,
        self.subject_1_speed = subject_1_speed,
        self.subject_1_location = subject_1_location,
        self.subject_1_travel_heading = subject_1_travel_heading,

        self.subject_2_id = subject_2_id,
        self.subject_2_name = subject_2_name,
        self.subject_2_speed = subject_2_speed,
        self.subject_2_location = subject_2_location,
        self.subject_2_travel_heading = subject_2_travel_heading,

        self.proximal_fix = proximal_fix
        self.proximity_distance_meters = proximity_distance_meters


SUBJECT_PROXIMITY_SCHEMA = {

    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Subject Proximity Schema",
        "type": "object",
        "properties": {
            "subject_1_name": {"type": "string", "title": "Subject 1 Name"},
            "subject_1_speed_kmhr": {"type": "number", "title": "Subject 1 Speed Kmhr"},
            "subject_1_heading": {"type": "number", "title": "Subject 1 Heading"},
            "subject_1_location": {"type": "string", "title": "Subject 1 location"},

            "subject_2_name": {"type": "string", "title": "Subject 2 Name"},
            "subject_2_speed_kmhr": {"type": "number", "title": "Subject 2 Speed Kmhr"},
            "subject_2_heading": {"type": "number", "title": "Subject 2 Heading"},
            "subject_2_location": {"type": "string", "title": "Subject 2 location"},

            "proximity_dist_meters": {"type": "number", "title": "Proximity Dist Meters"},
            "total_fix_count": {"type": "number", "title": "Total Fix Count"}
        }
    },
    "definition": [
        {
            "type": "fieldset",
            "title": "Analyzer Details",
            "htmlClass": "col-lg-12",
            "items": []
        },
        {
            "type": "fieldset",
            "htmlClass": "col-lg-6",
            "items": [
                "subject_1_name",
                "subject_1_location",
                "subject_1_speed_kmhr",
                "subject_1_heading"
            ]
        },
        {
            "type": "fieldset",
            "htmlClass": "col-lg-6",
            "items": [
                "subject_2_name",
                "subject_2_location",
                "subject_2_speed_kmhr",
                "subject_2_heading"
            ]
        },
        "proximity_dist_meters",
        "total_fix_count"
    ]
}
