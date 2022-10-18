from django.db.models import CharField, F, Max, Value
from django.db.models.functions import Cast, Concat

from accounts.models import User
from activity.models import Community, Event, EventType
from choices.models import Choice
from observations.models import Subject


def get_segments(kwargs, queryset):
    related_event = kwargs.get("event_id")
    if related_event:
        queryset = queryset.filter(eventrelatedsegments__event__id=related_event)
    return queryset


def calculate_event_schema_etag(view_instance, view_method, request, *args, **kwargs):
    user = request.user
    latest_et_update = Event.objects.all().aggregate(Max("event_type__updated_at")).get("event_type__updated_at__max")

    latest_choice_update = Choice.objects.all().aggregate(Max("updated_at")).get("updated_at__max")

    latest_reported_by_list = []
    for providence, people in Event.objects.get_reported_by(user):
        if people:
            for person in people:
                latest_reported_by_list.append(
                    (person.first_name, person.last_name) if isinstance(person, User) else person.updated_at
                )

    latest_reported_by_count = len(latest_reported_by_list)

    all_updates = (
        str(latest_et_update) + str(latest_choice_update) + str(latest_reported_by_count) + str(latest_reported_by_list)
    )
    return str(hash(all_updates))


def calculate_event_etag(view_instance, view_method, request, *args, **kwargs):
    instance = view_instance.get_object()
    return str(hash(instance.updated_at))


def generate_reported_by_lookup():
    user_qs = (
        User.objects.all()
        .annotate(
            internal_id=Cast("id", CharField()),
            value=F("username"),
            kind=Value("user", output_field=CharField()),
            display_value=Concat("first_name", Value(" "), "last_name"),
        )
        .values_list("internal_id", "value", "kind", "display_value")
    )
    community_qs = (
        Community.objects.all()
        .annotate(
            internal_id=Cast("id", CharField()),
            value=F("name"),
            kind=Value("community", output_field=CharField()),
            display_value=F("name"),
        )
        .values_list("internal_id", "value", "kind", "display_value")
    )
    reported_by_qs = (
        Subject.objects.all()
        .annotate(
            internal_id=Cast("id", CharField()),
            value=Cast("id", CharField()),
            kind=Value("subject", output_field=CharField()),
            display_value=F("name"),
        )
        .values_list("internal_id", "value", "kind", "display_value")
    )

    reported_by_list = reported_by_qs.union(user_qs, community_qs)

    reported_by_map = dict((x[0], {"value": x[1], "kind": x[2], "display": x[3]}) for x in reported_by_list)
    return reported_by_map


def generate_event_type_cache():
    event_types = EventType.objects.all().values("id", "value", "display", "schema")
    event_types_map = dict((event_type["id"], event_type) for event_type in event_types)
    return event_types_map
