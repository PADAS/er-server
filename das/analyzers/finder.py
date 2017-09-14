from analyzers.immobility import ImmobilityAnalyzer
from analyzers.geofence import GeofenceAnalyzer
from analyzers.environmental import EnvironmentalAnalyzer
from analyzers.speed import LowSpeedAnalyzer

subject_analyzers = (ImmobilityAnalyzer, EnvironmentalAnalyzer, GeofenceAnalyzer, LowSpeedAnalyzer)


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
