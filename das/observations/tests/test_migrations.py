import pytest

from observations.migration_utils import (
    SubjectSubTypeLoader,
    TenantSubjectSubTypeLoader,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectSubTypeLoader:
    def test_subject_subtype_loader_doesnt_repeat_new_subtypes(self):
        loader_one = SubjectSubTypeLoader(subject_type_value="wildlife")
        loader_two = SubjectSubTypeLoader(subject_type_value="wildlife")

        assert loader_one._subject_subtypes is not loader_two._subject_subtypes


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestTenantSubjectSubTypeLoader:
    def test_subject_subtype_loader_doesnt_repeat_new_subtypes(self):
        loader_one = TenantSubjectSubTypeLoader(subject_type_value="wildlife")
        loader_two = TenantSubjectSubTypeLoader(subject_type_value="wildlife")

        assert loader_one.subject_subtypes is not loader_two.subject_subtypes
