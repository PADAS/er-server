from analyzers.immobility import ImmobilityAnalyzer
from analyzers.geofence import GeofenceAnalyzer

subject_analyzers = (ImmobilityAnalyzer, GeofenceAnalyzer, )


def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)
