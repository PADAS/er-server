from observations.models import SubjectSource


class TwoWaySubjectSourceMixin:
    two_way_subject_sources = {}

    SUBJECT_ID_MAPPING = dict(Subject="id", SubjectGroup="subjects__id")

    def _get_two_way_sources(self, queryset):

        self.two_way_subject_sources = {}
        queryset_model_name = queryset.model.__name__

        try:
            subject_id_name = self.SUBJECT_ID_MAPPING[queryset_model_name]
        except KeyError:
            raise ValueError(f"{queryset_model_name} Not yet supported.")

        subject_sources = SubjectSource.objects.filter(
            subject__in=queryset.values(subject_id_name)
        )

        subject_sources = subject_sources.by_two_way_messaging_enabled(
        ).values(
            'id', 'subject_id', 'source_id', 'source__provider__display_name',
            'two_way_messaging', 'source_two_way_messaging'
        )

        for subject_source in subject_sources:
            source_id = subject_source["source_id"]
            if source_id not in self.two_way_subject_sources:
                self.two_way_subject_sources[source_id] = {}
            self.two_way_subject_sources[source_id][subject_source["id"]
                                                    ] = subject_source
