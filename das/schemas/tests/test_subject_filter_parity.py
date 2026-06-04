"""V1 → V2 Subject filter parity tests.

For each real-world V1 DynamicChoice criteria pattern observed in production,
verify that the equivalent V2 query parameters on the ``schemas:subjects``
endpoint return the **same set of Subject IDs** as the raw ORM filter.

Reference: V1 applies criteria via
    Subject.objects.filter(*criteria).filter(is_active=True)
where *criteria is a list of (field, value) tuples unpacked as positional args
to Django's QuerySet.filter().

Broken V1 patterns (excluded from parity tests)
------------------------------------------------
The following V1 criteria exist in production data but raise Django
``FieldError`` or are logically broken.  They are **not tested** here
because those V1 schemas were never rendering correctly:

- ``common_name_id__contains`` — ``FieldError: Related Field got invalid
  lookup: contains``.  FK field does not support ``contains``.
- ``subject_type=vehicle`` — ``FieldError``.  ``subject_type`` is a Python
  ``@property`` on Subject, not a database column.
- ``allRhino`` — ``JSONDecodeError``.  Raw string, not a JSON list.  V1
  catches this and returns ``[]``.
- ``subject_subtype=X, subject_subtype=Y`` (two subtypes ANDed) — Valid
  ORM but logically broken: a Subject has exactly one subtype so AND of
  two exclusive values always returns ∅.
"""

from __future__ import annotations

import pytest

from django.urls import reverse

from factories import SubjectFactory, SubjectSubTypeFactory, SubjectTypeFactory
from observations.models import CommonName, Subject, SubjectGroup

# ---------------------------------------------------------------------------
# Shared dataset fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def parity_dataset():
    """Create a rich dataset covering all V1 filter patterns.

    Returns a dict of subject references keyed by a short label so individual
    parametrized tests can express expected results concisely.
    """
    # --- SubjectTypes ---
    st_wildlife = SubjectTypeFactory.create(value="wildlife_pt")
    st_person = SubjectTypeFactory.create(value="person_pt")
    st_vehicle = SubjectTypeFactory.create(value="vehicle_pt")

    # --- SubjectSubTypes ---
    sst_rhino = SubjectSubTypeFactory.create(value="rhino_pt", subject_type=st_wildlife)
    sst_cougar = SubjectSubTypeFactory.create(value="cougar_pt", subject_type=st_wildlife)
    sst_elephant = SubjectSubTypeFactory.create(value="elephant_pt", subject_type=st_wildlife)
    sst_er_mobile = SubjectSubTypeFactory.create(value="er_mobile_pt", subject_type=st_person)
    sst_ranger = SubjectSubTypeFactory.create(value="ranger_pt", subject_type=st_person)
    sst_car = SubjectSubTypeFactory.create(value="car_pt", subject_type=st_vehicle)

    # --- CommonNames ---
    cn_black_rhino = CommonName.objects.create(
        value="black_rhino_pt",
        display="Black Rhino",
        subject_subtype=sst_rhino,
    )
    cn_white_rhino = CommonName.objects.create(
        value="white_rhino_pt",
        display="White Rhino",
        subject_subtype=sst_rhino,
    )
    cn_lion = CommonName.objects.create(
        value="lion_pt",
        display="Lion",
        subject_subtype=sst_cougar,
    )

    # --- Subjects ---
    s = {}
    s["br_male"] = SubjectFactory.create(
        name="BR Male",
        subject_subtype=sst_rhino,
        common_name=cn_black_rhino,
        additional={"sex": "male", "age": "adult"},
    )
    s["br_female"] = SubjectFactory.create(
        name="BR Female",
        subject_subtype=sst_rhino,
        common_name=cn_black_rhino,
        additional={"sex": "female", "age": "adult"},
    )
    s["br_unknown"] = SubjectFactory.create(
        name="BR Unknown",
        subject_subtype=sst_rhino,
        common_name=cn_black_rhino,
        additional={"sex": "unknown"},
    )
    s["wr_male"] = SubjectFactory.create(
        name="WR Male",
        subject_subtype=sst_rhino,
        common_name=cn_white_rhino,
        additional={"sex": "male"},
    )
    s["wr_female"] = SubjectFactory.create(
        name="WR Female",
        subject_subtype=sst_rhino,
        common_name=cn_white_rhino,
        additional={"sex": "female"},
    )
    s["rhino_calf"] = SubjectFactory.create(
        name="Rhino Calf",
        subject_subtype=sst_rhino,
        common_name=cn_black_rhino,
        additional={"sex": "unknown", "age": "calf"},
    )
    s["cougar1"] = SubjectFactory.create(
        name="Cougar One",
        subject_subtype=sst_cougar,
    )
    s["elephant_male"] = SubjectFactory.create(
        name="Elephant Male",
        subject_subtype=sst_elephant,
        additional={"sex": "male"},
    )
    s["elephant_female"] = SubjectFactory.create(
        name="Elephant Female",
        subject_subtype=sst_elephant,
        additional={"sex": "female"},
    )
    s["mobile1"] = SubjectFactory.create(
        name="Mobile One",
        subject_subtype=sst_er_mobile,
    )
    s["ranger1"] = SubjectFactory.create(
        name="Ranger One",
        subject_subtype=sst_ranger,
    )
    s["car1"] = SubjectFactory.create(
        name="Car One",
        subject_subtype=sst_car,
    )
    s["lion1"] = SubjectFactory.create(
        name="Lion One",
        subject_subtype=sst_cougar,
        common_name=cn_lion,
    )
    s["inactive_rhino"] = SubjectFactory.create(
        name="Inactive Rhino",
        subject_subtype=sst_rhino,
        common_name=cn_black_rhino,
        is_active=False,
        additional={"sex": "male"},
    )

    # --- Groups ---
    grp_pumas = SubjectGroup.objects.create(name="Pumas_pt")
    grp_pumas.subjects.add(s["cougar1"])

    grp_subjects = SubjectGroup.objects.create(name="Subjects_pt")
    grp_subjects.subjects.add(s["mobile1"], s["ranger1"])

    grp_dcs = SubjectGroup.objects.create(name="DCS_Team_pt")
    grp_dcs.subjects.add(s["ranger1"])

    grp_rhinos = SubjectGroup.objects.create(name="BlackRhino_pt")
    grp_rhinos.subjects.add(s["br_male"], s["br_female"], s["br_unknown"])

    grp_wr = SubjectGroup.objects.create(name="WhiteRhino_pt")
    grp_wr.subjects.add(s["wr_male"], s["wr_female"])

    return s


def _v1_orm_ids(criteria: list[tuple[str, str]]) -> set[str]:
    """Simulate V1 DynamicChoice: Subject.objects.filter(*criteria).filter(is_active=True)."""
    qs = Subject.objects.filter(*criteria).filter(is_active=True)
    return {str(pk) for pk in qs.values_list("id", flat=True)}


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------
#
# Each entry is:
#   (test_id, v1_criteria, v2_query_string, expected_subject_keys)
#
# v1_criteria: list of (field, value) tuples passed to .filter(*criteria)
# v2_query_string: query params appended to the endpoint URL
# expected_subject_keys: labels from parity_dataset that should appear

PARITY_CASES = [
    # --- Pattern 1: common_name_id exact ---
    (
        "common_name_id_exact",
        [("common_name_id", "black_rhino_pt")],
        "common_name=black_rhino_pt",
        {"br_male", "br_female", "br_unknown", "rhino_calf"},
    ),
    (
        "common_name_id_white_rhino",
        [("common_name_id", "white_rhino_pt")],
        "common_name=white_rhino_pt",
        {"wr_male", "wr_female"},
    ),
    # --- Pattern 2: subject_subtype exact ---
    (
        "subject_subtype_er_mobile",
        [("subject_subtype", "er_mobile_pt")],
        "subject_subtypes=er_mobile_pt",
        {"mobile1"},
    ),
    (
        "subject_subtype_ranger",
        [("subject_subtype", "ranger_pt")],
        "subject_subtypes=ranger_pt",
        {"ranger1"},
    ),
    (
        "subject_subtype_rhino",
        [("subject_subtype", "rhino_pt")],
        "subject_subtypes=rhino_pt",
        {"br_male", "br_female", "br_unknown", "wr_male", "wr_female", "rhino_calf"},
    ),
    # --- Pattern 3: subject_subtype + groups__name ---
    (
        "subtype_and_group",
        [("subject_subtype", "cougar_pt"), ("groups__name", "Pumas_pt")],
        "subject_subtypes=cougar_pt&group_name=Pumas_pt",
        {"cougar1"},
    ),
    (
        "er_mobile_and_group",
        [("subject_subtype", "er_mobile_pt"), ("groups__name", "Subjects_pt")],
        "subject_subtypes=er_mobile_pt&group_name=Subjects_pt",
        {"mobile1"},
    ),
    (
        "ranger_and_group",
        [("subject_subtype", "ranger_pt"), ("groups__name", "Subjects_pt")],
        "subject_subtypes=ranger_pt&group_name=Subjects_pt",
        {"ranger1"},
    ),
    # --- Pattern 4: common_name_id + additional ---
    (
        "cn_and_additional_sex_male",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "male")],
        "common_name=black_rhino_pt&additional__sex=male",
        {"br_male"},
    ),
    (
        "cn_and_additional_sex_female",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "female")],
        "common_name=black_rhino_pt&additional__sex=female",
        {"br_female"},
    ),
    (
        "cn_and_additional_sex_unknown",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "unknown")],
        "common_name=black_rhino_pt&additional__sex=unknown",
        {"br_unknown", "rhino_calf"},
    ),
    (
        "wr_and_additional_sex_male",
        [("common_name_id", "white_rhino_pt"), ("additional__sex", "male")],
        "common_name=white_rhino_pt&additional__sex=male",
        {"wr_male"},
    ),
    (
        "wr_and_additional_sex_female",
        [("common_name_id", "white_rhino_pt"), ("additional__sex", "female")],
        "common_name=white_rhino_pt&additional__sex=female",
        {"wr_female"},
    ),
    # --- Pattern 5: contains on common_name value (search) ---
    # NOTE: V1 data also shows ``common_name_id__contains`` but that is an
    # invalid Django ORM lookup (contains on a FK field).  The working V1
    # pattern is ``common_name__value__contains``.
    (
        "common_name_value_contains_rhino",
        [("common_name__value__contains", "rhino_pt")],
        "common_name_search=rhino_pt",
        {"br_male", "br_female", "br_unknown", "wr_male", "wr_female", "rhino_calf"},
    ),
    # --- Pattern 7: subject_subtype + additional ---
    (
        "subtype_rhino_age_calf",
        [("subject_subtype", "rhino_pt"), ("additional__age", "calf")],
        "subject_subtypes=rhino_pt&additional__age=calf",
        {"rhino_calf"},
    ),
    (
        "subtype_elephant_sex_female",
        [("subject_subtype", "elephant_pt"), ("additional__sex", "female")],
        "subject_subtypes=elephant_pt&additional__sex=female",
        {"elephant_female"},
    ),
    # --- Pattern 8: groups__name alone ---
    (
        "group_name_only",
        [("groups__name", "DCS_Team_pt")],
        "group_name=DCS_Team_pt",
        {"ranger1"},
    ),
    # --- Pattern 9: groups__name__in (multi-group) ---
    (
        "group_name_in_multi",
        [("groups__name__in", ["BlackRhino_pt", "WhiteRhino_pt"])],
        "group_name=BlackRhino_pt,WhiteRhino_pt",
        {"br_male", "br_female", "br_unknown", "wr_male", "wr_female"},
    ),
    # --- Pattern 10: common_name FK field (equivalent to common_name_id) ---
    (
        "common_name_fk_field",
        [("common_name", "lion_pt")],
        "common_name=lion_pt",
        {"lion1"},
    ),
    # --- Pattern 11: subject_subtype__value (equivalent to subject_subtype) ---
    (
        "subject_subtype_value_explicit",
        [("subject_subtype__value", "elephant_pt")],
        "subject_subtypes=elephant_pt",
        {"elephant_male", "elephant_female"},
    ),
    # --- Pattern 12: empty criteria ---
    (
        "empty_criteria",
        [],
        "",
        None,  # special: we just check V1 == V2, no fixed expected set
    ),
]


@pytest.mark.django_db
class TestV1V2SubjectFilterParity:
    """For each production V1 criteria pattern, confirm the V2 endpoint
    returns the same Subject IDs as the direct ORM query."""

    @pytest.mark.parametrize(
        "test_id, v1_criteria, v2_query, expected_keys",
        PARITY_CASES,
        ids=[c[0] for c in PARITY_CASES],
    )
    def test_v1_v2_parity(
        self,
        superuser_client,
        parity_dataset,
        test_id,
        v1_criteria,
        v2_query,
        expected_keys,
    ):
        s = parity_dataset

        # --- V1 path: raw ORM ---
        v1_ids = _v1_orm_ids(v1_criteria)

        # --- V2 path: endpoint ---
        url = reverse("schemas:subjects")
        full_url = f"{url}?{v2_query}" if v2_query else url
        response = superuser_client.get(full_url)
        assert response.status_code == 200
        v2_ids = set(response.json()["enum"])

        # --- Parity assertion ---
        # Both paths must agree on the dataset subjects.
        # We restrict comparison to subjects from our fixture to avoid
        # pollution from other test data in --reuse-db.
        fixture_ids = {str(subj.id) for subj in s.values()}
        v1_fixture = v1_ids & fixture_ids
        v2_fixture = v2_ids & fixture_ids

        assert v1_fixture == v2_fixture, (
            f"[{test_id}] V1 and V2 returned different fixture subjects.\n"
            f"  V1 only: {v1_fixture - v2_fixture}\n"
            f"  V2 only: {v2_fixture - v1_fixture}"
        )

        # --- Explicit expected set (when provided) ---
        if expected_keys is not None:
            expected_ids = {str(s[k].id) for k in expected_keys}
            assert v1_fixture == expected_ids, (
                f"[{test_id}] V1 ORM did not match expected keys.\n"
                f"  Expected: {expected_keys}\n"
                f"  Got IDs (V1): {v1_fixture}\n"
                f"  Expected IDs: {expected_ids}"
            )
            assert v2_fixture == expected_ids, (
                f"[{test_id}] V2 endpoint did not match expected keys.\n"
                f"  Expected: {expected_keys}\n"
                f"  Got IDs (V2): {v2_fixture}\n"
                f"  Expected IDs: {expected_ids}"
            )


# ---------------------------------------------------------------------------
# Edge-case: V1 `is_active` handled by existing include_inactive param
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsActiveParity:
    """V1 criteria ``is_active=True`` is implicitly handled by the V2 endpoint
    which excludes inactive subjects by default (via check_to_include_inactive_subjects).
    Passing ``?include_inactive=true`` overrides this."""

    def test_inactive_excluded_by_default(self, superuser_client, parity_dataset):
        s = parity_dataset
        url = reverse("schemas:subjects")
        response = superuser_client.get(f"{url}?common_name=black_rhino_pt")

        assert response.status_code == 200
        consts = set(response.json()["enum"])
        assert str(s["inactive_rhino"].id) not in consts
        assert str(s["br_male"].id) in consts

    def test_inactive_included_when_requested(self, superuser_client, parity_dataset):
        s = parity_dataset
        url = reverse("schemas:subjects")
        response = superuser_client.get(f"{url}?common_name=black_rhino_pt&include_inactive=true")

        assert response.status_code == 200
        consts = set(response.json()["enum"])
        assert str(s["inactive_rhino"].id) in consts
        assert str(s["br_male"].id) in consts


# ---------------------------------------------------------------------------
# Edge-case: case-sensitivity of contains vs icontains
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestContainsCaseSensitivity:
    """V1 uses ``common_name__value__contains`` (case-sensitive) while V2
    ``common_name_search`` maps to ``icontains``.  V2 is a superset: it
    never misses a V1 match but may return additional case-variant matches."""

    def test_icontains_is_superset_of_contains(self, superuser_client):
        subtype = SubjectSubTypeFactory.create(value="case_parity")
        cn_upper = CommonName.objects.create(
            value="Black_Rhino_CS",
            display="Black Rhino",
            subject_subtype=subtype,
        )
        cn_lower = CommonName.objects.create(
            value="black_rhino_cs",
            display="Black Rhino Lower",
            subject_subtype=subtype,
        )
        s_upper = SubjectFactory.create(subject_subtype=subtype, common_name=cn_upper)
        s_lower = SubjectFactory.create(subject_subtype=subtype, common_name=cn_lower)

        # V1: case-sensitive contains (via FK traversal)
        v1_ids = {
            str(pk)
            for pk in Subject.objects.filter(
                common_name__value__contains="Black_Rhino",
            ).values_list("id", flat=True)
        }

        # V2: case-insensitive search
        url = reverse("schemas:subjects")
        response = superuser_client.get(f"{url}?common_name_search=Black_Rhino")
        v2_ids = set(response.json()["enum"])

        # V1 only matches the uppercase version
        assert str(s_upper.id) in v1_ids
        assert str(s_lower.id) not in v1_ids

        # V2 matches both (superset)
        assert str(s_upper.id) in v2_ids
        assert str(s_lower.id) in v2_ids

        # V2 is a superset of V1
        assert v1_ids.issubset(v2_ids)
