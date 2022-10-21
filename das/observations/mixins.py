import uuid

from django.contrib.postgres.fields import jsonb
from django.db.models import Q

from observations import models


class FilterMixin(object):

    def by_id(self, primary_keys):
        if isinstance(primary_keys, str):
            primary_keys = [uuid.UUID(pk.strip())
                            for pk in primary_keys.split(',')]
        return self.filter(id__in=primary_keys)


class TwoWaySubjectSourceMixin(object):
    two_way_subject_sources = {}

    def _get_two_way_sources(self, queryset):
        lookup_field = {
            "Subject": "id",
            "SubjectGroup": "subjects__id",
        }
        self.two_way_subject_sources = {}
        queryset_object = str(queryset.model.__name__)

        try:
            subjects = lookup_field[queryset_object]
        except KeyError:
            raise ValueError(f"{queryset_object} Not yet supported.")

        if queryset_object == "SubjectGroup":
            queryset = self._get_children_subject_groups(queryset)

        subject_sources = models.SubjectSource.objects.filter(
            subject__in=queryset.values(subjects).all()
        )

        subject_sources = subject_sources.annotate(
            two_way_messaging=jsonb.KeyTransform(
                'two_way_messaging', 'source__provider__additional'),
            source_two_way_messaging=jsonb.KeyTransform(
                'two_way_messaging', 'source__additional')
        ).exclude(
            Q(two_way_messaging__isnull=True) | Q(two_way_messaging=False) | (
                Q(two_way_messaging=True) & (
                    Q(source_two_way_messaging=False,
                        source_two_way_messaging__isnull=False)
                )
            )

        ).prefetch_related(
            'source',
            'source__provider'
        ).values(
            'id', 'subject_id', 'source_id', 'source__provider__display_name', 'two_way_messaging', 'source_two_way_messaging'
        )

        for source in subject_sources:
            source_id = source["source_id"]
            if source_id not in self.two_way_subject_sources:
                self.two_way_subject_sources[source_id] = {}
            self.two_way_subject_sources[source_id][source["id"]] = source

    def _get_children_subject_groups(self, queryset):
        subject_groups_id = {str(subject_group.id)
                             for subject_group in queryset}
        for subject_group in queryset:
            subject_groups_id |= self._get_nested_subject_groups_id(
                subject_group.id)

        return models.SubjectGroup.objects.filter(id__in=subject_groups_id)

    def _get_nested_subject_groups_id(self, subject_group_id: str) -> set:
        subject_groups = models.SubjectGroup.objects.get_nested_groups(
            subject_group_id)
        return {str(subject_group.id) for subject_group in subject_groups}
