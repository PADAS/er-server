from rest_framework import serializers

from accounts.serializers import (
    get_user_display,
    UserDisplaySerializer
)
from activity.serializers.helpers import get_update_type
from revision.manager import AC_UPDATED


class BaseSerializer(serializers.Serializer):
    """This serves as the base class from which all other serializers extend.

    It contains fields common to all API resources in the app.
    """

    id = serializers.CharField(read_only=True)

    def __init__(self, *args, **kwargs):
        excludes = kwargs.pop('excludes', [])

        self.clear_excludes(excludes)

        super().__init__(*args, **kwargs)

    # TODO Leverage on metaclass
    def clear_excludes(self, excludes):
        list(
            map(
                lambda x: self.fields.pop(x, None),
                excludes
            )
        )


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
