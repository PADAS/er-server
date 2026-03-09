from analyzers.environmental import EnvironmentalAnalyzer
from analyzers.geofence import GeofenceAnalyzer
from analyzers.immobility import ImmobilityAnalyzer
from analyzers.movement_clustering import MovementClusterAnalyzer
from analyzers.observation_attribute import ObservationAttributeAnalyzer
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.speed import LowSpeedPercentileAnalyzer, LowSpeedWilcoxAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer

subject_analyzers = (
    ImmobilityAnalyzer,
    EnvironmentalAnalyzer,
    GeofenceAnalyzer,
    LowSpeedPercentileAnalyzer,
    LowSpeedWilcoxAnalyzer,
    FeatureProximityAnalyzer,
    SubjectProximityAnalyzer,
    ObservationAttributeAnalyzer,
    MovementClusterAnalyzer,
)


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
