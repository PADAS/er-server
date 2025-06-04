import versatileimagefield.files
from versatileimagefield.utils import IMAGE_SETS

from django.urls import reverse

import usercontent.serializers
import utils
from accounts.serializers import UserDisplaySerializer
from revision.manager import ACTION_RELATION_DELETED, ACTION_UPDATED

# Make dictionaries from the IMAGE_SETS, to make lookups a little easier.
IMAGE_RENDITION_SETS = dict((k, dict(v)) for k, v in IMAGE_SETS.items())


class FileSerializerMixin:
    def pre_create(self, validated_data):
        """The inheriting class can override create(), but we still need
        to validate the incomind file content data

        Args:
            validated_data (dict): validated_data

        Returns:
            dict: validated_data
        """
        ser = usercontent.serializers.UserContentSerializer(
            data=dict(
                file=self.context["request"].data["filecontent.file"],
            ),
            context={"request": self.context["request"]},
        )

        ser.is_valid(raise_exception=True)
        filecontent = ser.create(ser.validated_data)

        validated_data.pop("filecontent.file", None)

        validated_data["usercontent"] = filecontent

        return validated_data

    def create(self, validated_data):
        """standard serializer create. Calls our pre_create first
        then the next in line.

        Args:
            validated_data (dict): validated data

        Returns:
            any: the object
        """
        return super().create(self.pre_create(validated_data))

    @property
    def parent_name(self):
        raise NotImplementedError()

    def get_instance_parent_id(self, instance):
        raise NotImplementedError()

    def get_update_type(self, revision, previous_revisions=[]):
        raise NotImplementedError()

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep["updates"] = self.render_updates(instance)

        if "request" in self.context:
            request = self.context["request"]
            rep["url"] = utils.add_base_url(
                request,
                reverse(
                    f"{self.parent_name}-view-file",
                    args=[
                        self.get_instance_parent_id(instance),
                        instance.id,
                    ],
                ),
            )

            # If attached usercontent is an ImageFileField, then render urls
            # for renditions.
            if isinstance(instance.usercontent.file, (versatileimagefield.files.VersatileImageFieldFile,)):
                # Image Sizes
                image_sizes = {}
                # '('thumbnail', 'large'):
                for size in IMAGE_RENDITION_SETS["default"].keys():
                    image_sizes[size] = utils.add_base_url(
                        request,
                        reverse(
                            f"{self.parent_name}-view-file-size",
                            args=[
                                self.get_instance_parent_id(instance),
                                instance.id,
                                size,
                                instance.usercontent.filename,
                            ],
                        ),
                    )
                if image_sizes:
                    rep["images"] = image_sizes

        # Promote some usercontent attributes.
        rep["filename"] = rep["usercontent"].get("filename")
        rep["file_type"] = rep["usercontent"].get("file_type")

        try:
            rep["icon_url"] = rep["images"]["icon"]
        except KeyError:
            rep["icon_url"] = rep["usercontent"].get("icon_url")

        # Prune some unnecessary attributes.
        for att in ("usercontent", self.parent_name, "usercontent_id", "usercontent_type"):
            rep.pop(att, None)

        return rep

    def render_updates(self, file):
        def get_action(revision):
            return revision.get_action_display()

        return [
            dict(
                message=f"File {get_action(revision)}: {file.usercontent.filename}",
                time=revision.revision_at.isoformat(),
                text=revision.data.get("text", ""),
                user=UserDisplaySerializer().to_representation(revision.user),
                type=self.get_update_type(revision),
            )
            for revision in file.revision.all_user()
        ]

    def is_valid(self, raise_exception=False):
        try:
            r = super().is_valid(raise_exception=raise_exception)
        except Exception as e:
            raise e
        return r


class RevisionMixin:
    def get_action(self, revision, field_mapping=None, verbose_name=None):
        if revision.action == ACTION_UPDATED:
            fieldnames = [field_mapping[k].format(v) for k, v in revision.data.items() if k in field_mapping]
            return "{0} fields: {1}".format(revision.get_action_display(), ", ".join(fieldnames))
        elif revision.action == ACTION_RELATION_DELETED:
            field_mapping = {"message": "Description", "related_query_name": "{}"}
            fieldnames = [
                field_mapping[k].format(revision.data[k]) for k, v in revision.data.items() if k in field_mapping
            ]
            return "{0} fields: {1}".format(revision.get_action_display(), ", ".join(fieldnames))

        return f"{verbose_name} {revision.get_action_display()}" if verbose_name else revision.get_action_display()

    def get_patrol_update_type(self, revision, item="patrol"):
        field_keys = ("state",)
        field_mapping = ((k, f"update_{item}_{k}") for k in field_keys)
        model_name = revision._meta.model_name
        action = revision.action
        data = revision.data
        if action == "added":
            return "add_{0}".format(model_name.replace("revision", ""))
        elif action == "updated":
            for k, v in field_mapping:
                if k in data:
                    return v
            return f"update_{item}"
        return "other"
