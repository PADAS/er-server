from analyzers.immobility import ImmobilityAnalyzer

subject_analyzers = (ImmobilityAnalyzer,)

def get_subject_analyzers(subject):

    for klass in subject_analyzers:
        yield from klass.get_subject_analyzers(subject)

