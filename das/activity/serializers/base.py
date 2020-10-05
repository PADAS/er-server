from rest_framework import serializers
from revision.manager import AC_UPDATED, AC_RELATION_DELETED
from collections import OrderedDict
import copy


class BaseSerializer(serializers.Serializer):
    """This serves as the base class from which all other serializers extend.
    It contains fields common to all API resources in the app.
    """

    id = serializers.UUIDField(read_only=True)

    def __init__(self, *args, **kwargs):
        self.excludes = kwargs.pop('excludes', [])
        self.includes = kwargs.pop('includes', [])

        super().__init__(*args, **kwargs)

    def get_fields(self):
        """
        Returns a dictionary of {field_name: field_instance}.
        """
        fields = OrderedDict()
        declared_fields = copy.deepcopy(self._declared_fields)

        if self.includes:
            for field_name in self.includes:

                if field_name in declared_fields:
                    fields[field_name] = declared_fields[field_name]

            return fields

        elif self.excludes:
            for field_name in declared_fields:

                if field_name not in self.excludes:
                    fields[field_name] = declared_fields[field_name]

            return fields
        else:
            return declared_fields

    def update(self, instance, validated_data):
        # Default update
        update_fields = []
        for k, v in validated_data.items():
            if getattr(instance, k) != v:
                setattr(instance, k, v)
                if k not in ('id',):
                    update_fields.append(k)

        if update_fields:
            instance.save()
        return instance


class RevisionMixin(serializers.Serializer):
    def get_action(self, revision):
        if revision.action == AC_UPDATED:
            field_mapping = {
                'state': 'State is {0}',  # Patrol Mappings
                'priority': 'Priority is {0}',
                'title': 'Title',
                'objective': 'Objective',

                'text': 'Note Text',  # Note Mappings

                'scheduled_start': 'Scheduled Start',  # Segment Mappings
                'time_range': 'Time_range',
                'leader_id': 'Leader id',
                'provenance': 'Leader',
                'patrol_type': 'Patrol Type is {0}',
                'start_location': 'Start Location',
                'end_location': 'End Location'
            }
            fieldnames = [field_mapping[k].format(v) for k, v in revision.data.items() if k in field_mapping]
            return '{0} fields: {1}'.format(revision.get_action_display(), ', '.join(fieldnames))
        elif revision.action == AC_RELATION_DELETED:
            field_mapping = {'message': 'Description',
                             'related_query_name': '{}'
                             }
            fieldnames = [field_mapping[k].format(revision.data[k]) for k, v in revision.data.items() if
                          k in field_mapping]
            return '{0} fields: {1}'.format(revision.get_action_display(), ', '.join(fieldnames))

        return revision.get_action_display()

    def get_patrol_update_type(self, revision, item='patrol'):
        field_keys = ('title', 'objective', 'state', 'priority',  # Patrol keys
                      'text',  # Note keys
                      'scheduled_start',  # Segment keys
                      'time_range', 'leader_id', 'provenance', 'patrol_type', 'start_location', 'end_location')
        field_mapping = ((k, f'update_{item}_{k}') for k in field_keys)
        model_name = revision._meta.model_name
        action = revision.action
        data = revision.data
        if action == 'added':
            return 'add_{0}'.format(model_name.replace('revision', ''))
        elif action == 'updated':
            for k, v in field_mapping:
                if k in data:
                    return v
            return 'update_patrol'
        return 'other'


class TimestampMixin(serializers.Serializer):
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)