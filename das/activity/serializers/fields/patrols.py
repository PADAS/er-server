from collections import OrderedDict

from rest_framework.serializers import RelatedField, ValidationError

from activity.models import PROVENANCE_CHOICES, Patrol, PatrolSegment, PatrolType
from core.serializers import GenericRelatedField


class LeaderRelatedField(GenericRelatedField):
    def get_field_mapping(self, label="Leader"):
        return super().get_field_mapping(label)

    def get_object_queryset(self):
        request = self.context.get("request")
        for p in PROVENANCE_CHOICES:
            provenance = p[0]
            values = list(PatrolSegment.objects.get_leader_for_provenance(provenance, request.user))
            if values:
                yield provenance, values


class PatrolRelatedField(RelatedField):
    queryset = Patrol.objects.all()

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return PatrolType.objects.get_by_value(data)
            except PatrolType.DoesNotExist:
                raise ValidationError(f"patrol_type: {data} does not exist")


class PatrolTypeRelatedField(RelatedField):
    def get_queryset(self):
        return PatrolType.objects.all_sort()

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            data = data if isinstance(data, str) else data.value
            try:
                return PatrolType.objects.get_by_value(data)
            except PatrolType.DoesNotExist:
                raise ValidationError(f"patrol_type: {data} does not exist")

    @property
    def choices(self):
        return OrderedDict(((row.value, row.display) for row in self.get_queryset()))
