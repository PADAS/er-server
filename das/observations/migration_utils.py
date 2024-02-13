import logging
from typing import Optional

from django.apps import apps

from utils.tenant.exceptions import TenantNotFoundException
from utils.tenant.managers import TenantContextManager, UnsetDASTenantContextManager

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


class TenantSubjectSubTypeLoader:
    def __init__(self, subject_type_value: str, new_subtypes: Optional[list] = None):
        self.subject_type_value = subject_type_value
        self.subject_subtypes = new_subtypes or list()

    def add_subject_subtype(self, display: str, value: str):
        if display and value:
            self.subject_subtypes.append({"display": display, "value": value})

        return self

    def load(self, unused, schema_editor):
        db_alias = schema_editor.connection.alias
        DASTenant = apps.get_model("core", "DASTenant")

        with UnsetDASTenantContextManager():
            all_tenants = list(DASTenant.objects.using(db_alias).all())

        for tenant in all_tenants:
            domain = tenant.domain
            logger.debug("Loading SubjectSubTypes %s for tenant %s", self.subject_subtypes, domain)
            try:
                with TenantContextManager(domain=domain):
                    SubjectSubType = apps.get_model("observations", "SubjectSubType")
                    SubjectType = apps.get_model("observations", "SubjectType")
                    subject_type = SubjectType.objects.using(db_alias).get(value=self.subject_type_value)

                    for subject_subtype in self.subject_subtypes:
                        defaults = {"display": subject_subtype["display"], "subject_type": subject_type}
                        _, created = SubjectSubType.objects.using(db_alias).get_or_create(
                            value=subject_subtype["value"], defaults=defaults
                        )
            except (DASTenant.DoesNotExist, TenantNotFoundException):
                logger.warning(
                    "DASTenant with domain %s does not exist in TMS, when adding new SubjectSubTypes for that domain",
                    domain,
                )
                raise
