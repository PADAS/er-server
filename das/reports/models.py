from django.db import models

from core.models import TimestampedModel, UUIDModel


class SourceProviderEvent(TimestampedModel, UUIDModel):
    source_provider = models.ForeignKey(
        "observations.SourceProvider",
        on_delete=models.CASCADE,
        related_name="events_reached_threshold",
        related_query_name="event_reached_threshold",
    )
    event = models.ForeignKey(
        "activity.Event",
        on_delete=models.CASCADE,
        related_name="sources_provider_event",
        related_query_name="source_provider_event",
    )


class SourceEvent(TimestampedModel, UUIDModel):
    source = models.ForeignKey(
        "observations.Source",
        on_delete=models.CASCADE,
        related_name="events_reached_threshold",
        related_query_name="event_reached_threshold",
    )
    event = models.ForeignKey(
        "activity.Event",
        on_delete=models.CASCADE,
        related_name="sources_event",
        related_query_name="source_event",
    )
