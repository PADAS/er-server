from analyzers.environmental import EnvironmentalAnalyzer
from analyzers.geofence import GeofenceAnalyzer
from analyzers.immobility import ImmobilityAnalyzer
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.speed import LowSpeedPercentileAnalyzer, LowSpeedWilcoxAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
from das.analyzers.observation_attribute import ObservationAttributeAnalyzer

subject_analyzers = (
    ImmobilityAnalyzer,
    EnvironmentalAnalyzer,
    GeofenceAnalyzer,
    LowSpeedPercentileAnalyzer,
    LowSpeedWilcoxAnalyzer,
    FeatureProximityAnalyzer,
    SubjectProximityAnalyzer,
    ObservationAttributeAnalyzer,
)


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
