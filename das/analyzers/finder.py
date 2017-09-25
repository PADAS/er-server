from analyzers.immobility import ImmobilityAnalyzer
from analyzers.geofence import GeofenceAnalyzer
from analyzers.environmental import EnvironmentalAnalyzer
from analyzers.speed import LowSpeedPercentileAnalyzer
from analyzers.speed import LowSpeedWilcoxAnalyzer

subject_analyzers = (ImmobilityAnalyzer, EnvironmentalAnalyzer, GeofenceAnalyzer, LowSpeedPercentileAnalyzer,
                     LowSpeedWilcoxAnalyzer)


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
