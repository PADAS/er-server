from analyzers.immobility import ImmobilityAnalyzer
from analyzers.geofence import GeofenceAnalyzer
from analyzers.environmental import EnvironmentalAnalyzer
from analyzers.speed import LowSpeedPercentileAnalyzer
from analyzers.speed import LowSpeedWilcoxAnalyzer
from analyzers.proximity import FeatureProximityAnalyzer
from analyzers.subject_proximity import SubjectProximityAnalyzer
subject_analyzers = (ImmobilityAnalyzer, EnvironmentalAnalyzer, GeofenceAnalyzer, LowSpeedPercentileAnalyzer,
                     LowSpeedWilcoxAnalyzer, FeatureProximityAnalyzer, SubjectProximityAnalyzer)

def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
