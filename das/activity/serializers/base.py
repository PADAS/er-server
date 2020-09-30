from rest_framework import serializers

from accounts.serializers import (
    get_user_display,
    UserDisplaySerializer
)
from activity.serializers.helpers import get_update_type
from revision.manager import AC_UPDATED
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
    updates = serializers.SerializerMethodField()

    def get_updates(self, obj):
        def get_action(revision):
            if revision.action == AC_UPDATED:
                field_mapping = {'text': 'Note Text'}
                fieldnames = [field_mapping[k] for k in revision.data.keys() if
                              k in field_mapping]
                return '{0} fields: {1}'.format(revision.get_action_display(),
                                                ', '.join(fieldnames))

            return revision.get_action_display()

        return [
            dict(
                message='Note {action}'.format(
                    action=get_action(revision),
                    user=get_user_display(revision.user)
                ),
                time=revision.revision_at.isoformat(),
                text=revision.data.get('text', ''),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=get_update_type(revision),
            )
            for revision in obj.revision.all_user()
        ]


class TimestampMixin(serializers.Serializer):
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)