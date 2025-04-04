from rest_framework.serializers import (
    CharField,
    Serializer,
    SerializerMethodField,
    UUIDField,
)

from observations.serializers import SubjectSerializer


class AllGroupsSerializer(Serializer):
    id = UUIDField(read_only=True)
    name = CharField(read_only=True)
    subjects = SerializerMethodField(read_only=True)
    subgroups = SerializerMethodField(read_only=True)

    def get_subgroups(self, obj):
        return [AllGroupsSerializer(group, context=self.context).data for group in obj.subgroups]

    def get_subjects(self, obj):
        subjects_cache = self.context.get("subjects_cache", {})
        serialized_subjects = []

        for subject in obj.subjects:
            if subject:
                if subject.id not in subjects_cache:
                    subjects_cache[subject.id] = SubjectSerializer(subject, context=self.context).data

                serialized_subjects.append(subjects_cache[subject.id])

        self.context["subjects_cache"] = subjects_cache
        return serialized_subjects
