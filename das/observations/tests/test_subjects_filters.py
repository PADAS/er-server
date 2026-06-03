"""
DB-backed integration tests for SubjectsView filtering via ``SubjectFilterSet``.

Covers:
- ``common_name`` exact filter — end-to-end through both phases of
  ``SubjectsView.get_queryset`` (phase-1 narrowing survives the phase-2
  ``union`` re-query via the ``id__in`` mechanism).
- ``subject_type`` exact filter.
- Each ``additional.*`` JSON exact filter (sex, species, age, gender).
- Combined filters AND together.
- Real JSONB numeric value (``{"age": 5}``) matched by ``?additional.age=5``.
- Repeated param → last-wins (QueryDict / raw URL string behaviour).
- Unknown ``additional.*`` param silently ignored (no 400, returns unfiltered set).
- No filter params → behaviour unchanged.
- Permission scoping: a non-superuser with limited subject-group permissions
  filtering by ``common_name`` must NOT see subjects outside their permitted
  groups (filters must not bypass ``by_user_subjects`` access control).
"""

from __future__ import annotations

import pytest

from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from factories import (
    PermissionSetFactory,
    SubjectFactory,
    SubjectGroupFactory,
    SubjectSubTypeFactory,
    UserFactory,
)
from observations.models import CommonName, SubjectSubType, SubjectType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_ids(response) -> set[str]:
    """Return the set of subject ID strings from either a paginated or unpaginated response."""
    data = response.data
    # SubjectsView uses OptionalResultsSetPagination (no default page_size), so
    # without an explicit page_size query param the response is a plain list.
    items = data["results"] if isinstance(data, dict) else data
    return {str(item["id"]) for item in items}


def _make_common_name(value: str, subtype: SubjectSubType, das_tenant) -> CommonName:
    """Create (or get) a ``CommonName`` with *value* as its PK."""
    cn, _ = CommonName.objects.get_or_create(
        value=value,
        defaults={"display": value.replace("_", " ").title(), "subject_subtype": subtype, "das_tenant": das_tenant},
    )
    return cn


# ---------------------------------------------------------------------------
# Fixtures for subjects with common_name, subject_type, and additional fields
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsViewCommonNameFilter:
    """End-to-end tests for ``common_name`` exact filter on SubjectsView.

    Tests exercise both phases of ``SubjectsView.get_queryset``: phase 1
    applies the FilterSet and narrows the queryset, phase 2 re-queries by
    ``id__in`` from the phase-1 result set.  The HTTP response is the
    authoritative proof that the narrowing survives both phases.
    """

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("subjects-list-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        wildlife_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_cn_test",
            defaults={"display": "Wildlife CN Test", "das_tenant": das_tenant},
        )
        subtype = SubjectSubTypeFactory(subject_type=wildlife_type, das_tenant=das_tenant)

        self.black_rhino_cn = _make_common_name("black_rhino_test", subtype, das_tenant)
        self.white_rhino_cn = _make_common_name("white_rhino_test", subtype, das_tenant)

        self.subject_a = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=self.black_rhino_cn,
        )
        self.subject_b = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=self.black_rhino_cn,
        )
        self.subject_c = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=self.white_rhino_cn,
        )
        self.subject_no_cn = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=None,
        )

    def test_common_name_filter_returns_matching_subjects(self):
        """Filtering by common_name returns only subjects with that FK value."""
        response = self.client.get(self.url, {"common_name": "black_rhino_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.subject_a.id) in ids
        assert str(self.subject_b.id) in ids
        assert str(self.subject_c.id) not in ids
        assert str(self.subject_no_cn.id) not in ids

    def test_common_name_filter_white_rhino_returns_correct_subject(self):
        """Filter by a different common name returns only the matching subject."""
        response = self.client.get(self.url, {"common_name": "white_rhino_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.subject_c.id) in ids
        assert str(self.subject_a.id) not in ids
        assert str(self.subject_b.id) not in ids

    def test_common_name_filter_nonexistent_value_returns_empty(self):
        """A common_name value that no subject has returns an empty result set."""
        response = self.client.get(self.url, {"common_name": "no_such_common_name_xyz"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.subject_a.id) not in ids
        assert str(self.subject_c.id) not in ids

    def test_common_name_is_exact_not_comma_list(self):
        """``common_name`` is an exact-match filter (CharFilter), NOT a comma-list IN filter.

        A comma-separated value such as ``black_rhino_test,white_rhino_test`` is
        treated as a single literal string that matches no subject.  This guards
        against accidentally switching to ``CharInFilter`` in future.
        """
        response = self.client.get(self.url, {"common_name": "black_rhino_test,white_rhino_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.subject_a.id) not in ids
        assert str(self.subject_c.id) not in ids

    def test_no_common_name_filter_returns_all_subjects(self):
        """Without any filter params the endpoint returns all created subjects."""
        response = self.client.get(self.url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.subject_a.id) in ids
        assert str(self.subject_b.id) in ids
        assert str(self.subject_c.id) in ids


# ---------------------------------------------------------------------------
# subject_type filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsViewSubjectTypeFilter:
    """Integration tests for ``subject_type`` exact filter on SubjectsView."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("subjects-list-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        self.vehicle_type, _ = SubjectType.objects.get_or_create(
            value="vehicle_st_test",
            defaults={"display": "Vehicle ST Test", "das_tenant": das_tenant},
        )
        self.wildlife_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_st_test",
            defaults={"display": "Wildlife ST Test", "das_tenant": das_tenant},
        )

        vehicle_subtype = SubjectSubTypeFactory(subject_type=self.vehicle_type, das_tenant=das_tenant)
        wildlife_subtype = SubjectSubTypeFactory(subject_type=self.wildlife_type, das_tenant=das_tenant)

        self.vehicle_subject = SubjectFactory(das_tenant=das_tenant, subject_subtype=vehicle_subtype)
        self.wildlife_subject = SubjectFactory(das_tenant=das_tenant, subject_subtype=wildlife_subtype)

    def test_filter_by_subject_type_vehicle_returns_vehicle_subjects(self):
        response = self.client.get(self.url, {"subject_type": "vehicle_st_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.vehicle_subject.id) in ids
        assert str(self.wildlife_subject.id) not in ids

    def test_filter_by_subject_type_wildlife_returns_wildlife_subjects(self):
        response = self.client.get(self.url, {"subject_type": "wildlife_st_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.wildlife_subject.id) in ids
        assert str(self.vehicle_subject.id) not in ids

    def test_filter_by_subject_type_unknown_returns_no_subjects(self):
        response = self.client.get(self.url, {"subject_type": "no_such_type_xyz"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.vehicle_subject.id) not in ids
        assert str(self.wildlife_subject.id) not in ids

    def test_subject_type_is_exact_not_comma_list(self):
        """``subject_type`` is an exact-match filter (CharFilter), NOT a comma-list IN filter.

        A comma-separated value such as ``vehicle_st_test,wildlife_st_test`` is
        treated as a single literal string that matches no subject.  This guards
        against accidentally switching to ``CharInFilter`` in future.
        """
        response = self.client.get(self.url, {"subject_type": "vehicle_st_test,wildlife_st_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.vehicle_subject.id) not in ids
        assert str(self.wildlife_subject.id) not in ids


# ---------------------------------------------------------------------------
# additional.* JSON field filters
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsViewAdditionalJsonFieldFilters:
    """Integration tests for ``additional.<key>`` JSONB exact filtering on SubjectsView."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("subjects-list-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        subtype = SubjectSubTypeFactory(das_tenant=das_tenant)

        self.female_lion = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            additional={"sex": "female", "species": "lion", "gender": "female"},
        )
        self.male_lion = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            additional={"sex": "male", "species": "lion", "gender": "male"},
        )
        self.female_cheetah = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            additional={"sex": "female", "species": "cheetah", "gender": "female"},
        )
        self.young_lion = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            additional={"sex": "male", "species": "lion", "age": "young"},
        )
        self.numeric_age = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            # Store age as a JSON number (not a string) to test text extraction.
            additional={"species": "rhino", "age": 5},
        )
        self.no_additional = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            additional={},
        )

    def test_filter_by_species_returns_matching_subjects(self):
        response = self.client.get(self.url, {"additional.species": "lion"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_lion.id) in ids
        assert str(self.male_lion.id) in ids
        assert str(self.young_lion.id) in ids
        assert str(self.female_cheetah.id) not in ids
        assert str(self.no_additional.id) not in ids

    def test_filter_by_sex_female_returns_female_subjects(self):
        response = self.client.get(self.url, {"additional.sex": "female"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_lion.id) in ids
        assert str(self.female_cheetah.id) in ids
        assert str(self.male_lion.id) not in ids
        assert str(self.young_lion.id) not in ids

    def test_filter_by_gender_male_returns_male_subjects(self):
        response = self.client.get(self.url, {"additional.gender": "male"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.male_lion.id) in ids
        assert str(self.female_lion.id) not in ids
        assert str(self.female_cheetah.id) not in ids

    def test_filter_by_age_string_returns_matching_subjects(self):
        response = self.client.get(self.url, {"additional.age": "young"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.young_lion.id) in ids
        assert str(self.female_lion.id) not in ids

    def test_filter_by_numeric_jsonb_age_matched_as_text(self):
        """A JSONB numeric value (``{"age": 5}``) must match ``?additional.age=5``.

        ``JSONFieldFilterSetMixin`` declares ``age`` as ``"type": "string"``,
        which causes ``KeyTextTransform`` to be used.  PostgreSQL extracts the
        number as the text ``"5"``, making the exact-string comparison succeed
        even though the stored value is a JSON integer.
        """
        response = self.client.get(self.url, {"additional.age": "5"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.numeric_age.id) in ids
        # "young" should not match "5"
        assert str(self.young_lion.id) not in ids

    def test_combined_species_and_sex_filters_narrow_results(self):
        """Two ``additional.*`` filters must AND together."""
        response = self.client.get(self.url, {"additional.species": "lion", "additional.sex": "female"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_lion.id) in ids
        assert str(self.male_lion.id) not in ids
        assert str(self.female_cheetah.id) not in ids

    def test_no_additional_params_returns_all_subjects(self):
        """Without any filter params all created subjects are returned."""
        response = self.client.get(self.url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_lion.id) in ids
        assert str(self.male_lion.id) in ids
        assert str(self.female_cheetah.id) in ids
        assert str(self.no_additional.id) in ids

    def test_unknown_additional_param_is_silently_ignored(self):
        """An undeclared ``additional.*`` param must NOT raise 400; it is silently ignored."""
        response = self.client.get(self.url, {"additional.unknown_field": "value"})
        assert response.status_code == 200
        ids = _get_ids(response)
        # No filtering applied → all fixture subjects still present.
        assert str(self.female_lion.id) in ids
        assert str(self.male_lion.id) in ids
        assert str(self.no_additional.id) in ids

    def test_last_wins_on_repeated_additional_species(self):
        """When ``additional.species`` is repeated, the last value wins.

        ``QueryDict.get()`` returns the last value for a repeated key, so
        ``?additional.species=lion&additional.species=cheetah`` filters to
        subjects with ``species == "cheetah"`` only.
        """
        url = self.url + "?additional.species=lion&additional.species=cheetah"
        response = self.client.get(url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_cheetah.id) in ids
        assert str(self.female_lion.id) not in ids
        assert str(self.male_lion.id) not in ids


# ---------------------------------------------------------------------------
# Combined common_name + additional.* filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsViewCombinedFilters:
    """Tests verifying that multiple filter params AND together correctly."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("subjects-list-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        wildlife_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_combined_test",
            defaults={"display": "Wildlife Combined Test", "das_tenant": das_tenant},
        )
        subtype = SubjectSubTypeFactory(subject_type=wildlife_type, das_tenant=das_tenant)
        self.black_rhino_cn = _make_common_name("black_rhino_combined_test", subtype, das_tenant)

        # Same common_name, different sex
        self.female_rhino = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=self.black_rhino_cn,
            additional={"sex": "female"},
        )
        self.male_rhino = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=self.black_rhino_cn,
            additional={"sex": "male"},
        )
        # Different common_name, same sex
        self.other_female = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=None,
            additional={"sex": "female"},
        )

    def test_common_name_and_additional_sex_both_apply(self):
        """``common_name`` and ``additional.sex`` must AND together."""
        response = self.client.get(
            self.url,
            {"common_name": "black_rhino_combined_test", "additional.sex": "female"},
        )
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.female_rhino.id) in ids
        assert str(self.male_rhino.id) not in ids
        assert str(self.other_female.id) not in ids

    def test_subject_type_and_additional_species_both_apply(self):
        """``subject_type`` and ``additional.species`` must AND together."""
        other_type, _ = SubjectType.objects.get_or_create(
            value="other_combined_test",
            defaults={"display": "Other Combined Test", "das_tenant": self.female_rhino.das_tenant},
        )
        other_subtype = SubjectSubTypeFactory(subject_type=other_type, das_tenant=self.female_rhino.das_tenant)
        # A subject with the right type but wrong species
        right_type_wrong_species = SubjectFactory(
            das_tenant=self.female_rhino.das_tenant,
            subject_subtype=SubjectSubTypeFactory(
                subject_type=SubjectType.objects.get(value="wildlife_combined_test"),
                das_tenant=self.female_rhino.das_tenant,
            ),
            additional={"species": "elephant"},
        )
        # A subject with the right species but wrong type
        wrong_type_right_species = SubjectFactory(
            das_tenant=self.female_rhino.das_tenant,
            subject_subtype=other_subtype,
            additional={"species": "rhino"},
        )
        # A subject with both matching
        right_both = SubjectFactory(
            das_tenant=self.female_rhino.das_tenant,
            subject_subtype=SubjectSubTypeFactory(
                subject_type=SubjectType.objects.get(value="wildlife_combined_test"),
                das_tenant=self.female_rhino.das_tenant,
            ),
            additional={"species": "rhino"},
        )

        response = self.client.get(
            self.url,
            {"subject_type": "wildlife_combined_test", "additional.species": "rhino"},
        )
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(right_both.id) in ids
        assert str(right_type_wrong_species.id) not in ids
        assert str(wrong_type_right_species.id) not in ids


# ---------------------------------------------------------------------------
# Permission scoping test
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsViewFilterWithPermissionScoping:
    """Verify that new filters do not bypass ``by_user_subjects`` access control.

    A non-superuser with access to only one subject group must not see subjects
    in other groups even when filtering by a ``common_name`` that is shared
    across groups.
    """

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("subjects-list-view")

        # Build the permission set the non-superuser needs to pass the
        # has_any_perms(VIEW_SUBJECT_PERMS) check in get_queryset.
        view_subject = Permission.objects.get(codename="view_subject")
        view_subjectgroup = Permission.objects.get_by_natural_key("view_subjectgroup", "observations", "subjectgroup")
        access_begins = Permission.objects.get(codename="access_begins_60")
        access_ends = Permission.objects.get(codename="access_ends_0")

        permitted_ps = PermissionSetFactory(das_tenant=das_tenant)
        permitted_ps.permissions.add(view_subject, view_subjectgroup, access_begins, access_ends)

        self.limited_user = UserFactory(is_superuser=False, das_tenant=das_tenant)
        self.limited_user.permission_sets.add(permitted_ps)

        # Shared common_name so both in-scope and out-of-scope subjects
        # would pass the common_name filter if scoping were bypassed.
        wildlife_type, _ = SubjectType.objects.get_or_create(
            value="wildlife_perm_test",
            defaults={"display": "Wildlife Perm Test", "das_tenant": das_tenant},
        )
        subtype = SubjectSubTypeFactory(subject_type=wildlife_type, das_tenant=das_tenant)
        shared_cn = _make_common_name("shared_rhino_perm_test", subtype, das_tenant)

        # Subject in the user's permitted group.
        self.permitted_subject = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=shared_cn,
        )
        # Subject NOT in the user's permitted group.
        self.forbidden_subject = SubjectFactory(
            das_tenant=das_tenant,
            subject_subtype=subtype,
            common_name=shared_cn,
        )

        # Grant the user access to permitted_subject's group only.
        permitted_group = SubjectGroupFactory(
            das_tenant=das_tenant,
            permission_sets=[permitted_ps],
        )
        permitted_group.subjects.add(self.permitted_subject)

        # forbidden_subject is in a separate group with no permission for this user.
        forbidden_group = SubjectGroupFactory(das_tenant=das_tenant)
        forbidden_group.subjects.add(self.forbidden_subject)

        self.client = APIClient()
        self.client.force_authenticate(user=self.limited_user)

    def test_common_name_filter_respects_permission_scoping(self):
        """Filter by common_name must not reveal out-of-scope subjects."""
        response = self.client.get(self.url, {"common_name": "shared_rhino_perm_test"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.permitted_subject.id) in ids
        assert str(self.forbidden_subject.id) not in ids

    def test_no_filter_respects_permission_scoping(self):
        """Without any filter, permission scoping still excludes out-of-scope subjects."""
        response = self.client.get(self.url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.permitted_subject.id) in ids
        assert str(self.forbidden_subject.id) not in ids
