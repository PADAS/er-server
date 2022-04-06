import uuid

from django.contrib.postgres.fields import jsonb
from django.db.models import Q


class FilterMixin(object):

    def by_id(self, primary_keys):
        if isinstance(primary_keys, str):
            primary_keys = [uuid.UUID(pk.strip())
                            for pk in primary_keys.split(',')]
        return self.filter(id__in=primary_keys)


class TwoWaySubjectSourceMixin(object):
    two_way_subject_sources = {}

    def _get_two_way_sources(self, queryset):
        from observations.models import SubjectSource

        self.two_way_subject_sources = {}
        queryset_object = str(queryset.model).split(".")[-1].replace("'>", "")

        subjects = ""
        if queryset_object == "Subject":
            subjects = "id"
        elif queryset_object == "SubjectGroup":
            subjects = "subjects__id"
        else:
            raise ValueError(f"{queryset_object} Not yet supported.")

        subject_sources = SubjectSource.objects.filter(
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
