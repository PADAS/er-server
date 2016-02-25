from activity.models import Event
from analyzers.models import all_analyzers


def get_or_create_analyzers_for_subject(subject):

    for klass in all_analyzers:
        analyzers = klass.objects.filter(subject=subject)
        if analyzers.exists():
            for analyzer in analyzers:
                yield analyzer
        else:
            # new it up
            analyzer = klass.objects.create(subject=subject)
            yield analyzer


def latest_event_for(subject, analyzer):
    """ Returns the most recent event or None for a given subject and analyzer """

    event = Event.objects \
        .filter(
            attachment__target_id=subject.id,
            provenance='analyzer',
            attributes__analyzer_type=analyzer.name) \
        .order_by('-created_at') \
        .first()

    return event
