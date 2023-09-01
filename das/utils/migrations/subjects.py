import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SubjectSubTypeLoader:
    def __init__(self, subject_type_value: str, new_subtypes: Optional[list] = None):
        self._subject_type_value = subject_type_value
        self._subject_subtypes = new_subtypes or list()

    def add_subject_subtype(self, display: str, value: str):
        if display and value:
            self._subject_subtypes.append({"display": display, "value": value})

        return self

    def load(self, apps, schema_editor):
        db_alias = schema_editor.connection.alias
        SubjectSubType = apps.get_model("observations", "SubjectSubType")
        SubjectType = apps.get_model("observations", "SubjectType")
        subject_type = SubjectType.objects.using(db_alias).get(value=self._subject_type_value)

        for subject_subtype in self._subject_subtypes:
            defaults = {"display": subject_subtype["display"], "subject_type": subject_type}
            _, created = SubjectSubType.objects.using(db_alias).get_or_create(
                value=subject_subtype["value"], defaults=defaults
            )

            if not created:
                logger.warning(
                    "Could not create '%s' subject subtype with value '%s'",
                    self._subject_type_value,
                    subject_subtype["value"],
                )
