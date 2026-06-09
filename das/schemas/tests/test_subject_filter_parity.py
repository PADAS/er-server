"""V1 → V2 Subject filter parity tests.

IMPORTANT — REMOVAL NOTICE
---------------------------
These tests exist **only** to validate the v1→v2 DynamicChoice schema migration.
They become obsolete once all v1 DynamicChoice schemas in production have been
migrated to v2 ``$ref`` schemas.  At that point the entire file (and the
``v1_migration_parity`` marker in pytest.ini) should be deleted.

Background
----------
For each real-world V1 DynamicChoice criteria pattern observed in production,
verify that the equivalent V2 query parameters on the ``schemas:subjects``
endpoint return the **same set of Subject IDs** as the raw ORM filter.

Reference: V1 applies criteria via
    Subject.objects.filter(*criteria).filter(is_active=True)
where *criteria is a list of (field, value) tuples unpacked as positional args
to Django's QuerySet.filter().

Excluded patterns (not ported — documented here for traceability)
-----------------------------------------------------------------
1. ``common_name__value__contains`` / ``common_name_search`` icontains, and the
   whole ``TestContainsCaseSensitivity`` class — non-exact lookups, deferred to
   a future operator-grammar PR.  Our endpoint is exact-only for ``common_name``.

2. Multi-value ``common_name`` (comma list) — our ``common_name`` param is
   single-exact; a comma-separated value is treated as a literal string.
   (Multi-group via ``subject_group`` comma IS supported and is ported.)

3. ``subject_type`` parity — ``subject_type=vehicle`` raises ``FieldError`` in V1
   (``subject_type`` is a Python ``@property``, not a DB column), so there is
   NO V1 behaviour to compare against.  ``subject_type`` is a NEW v2-only
   capability covered by ``observations/tests/test_subjects_filters.py``.

Broken V1 patterns (also excluded)
-----------------------------------
The following V1 criteria exist in production data but raise Django
``FieldError`` or are logically broken.  They are **not tested** here
because those V1 schemas were never rendering correctly:

- ``common_name_id__contains`` — ``FieldError: Related Field got invalid
  lookup: contains``.  FK field does not support ``contains``.
- ``allRhino`` — ``JSONDecodeError``.  Raw string, not a JSON list.  V1
  catches this and returns ``[]``.
- ``subject_subtype=X, subject_subtype=Y`` (two subtypes ANDed) — Valid
  ORM but logically broken: a Subject has exactly one subtype so AND of
  two exclusive values always returns the empty set.
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

    Returns a tuple ``(subjects, groups)`` where:
    - ``subjects`` is a dict of Subject references keyed by a short label.
    - ``groups`` is a dict of SubjectGroup references keyed by their name.

    Group nesting note
    ------------------
    All groups in this fixture are FLAT leaf groups (no child groups).  This
    is intentional: v1 ``groups__name=X`` is direct membership only (no nesting),
    but our ``SubjectsView`` with a single ``subject_group`` UUID expands to
    nested groups via ``get_nested_groups``.  By keeping groups flat,
    direct membership == nested expansion, so the v1/v2 parity assertion holds.
    DO NOT add child groups to any group in this fixture without updating all
    affected parity test cases; doing so would silently invalidate the parity
    comparison.
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

    # --- Groups (all FLAT — no children; see docstring above) ---
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

    groups = {
        "Pumas_pt": grp_pumas,
        "Subjects_pt": grp_subjects,
        "DCS_Team_pt": grp_dcs,
        "BlackRhino_pt": grp_rhinos,
        "WhiteRhino_pt": grp_wr,
    }

    return s, groups


def _v1_orm_ids(criteria: list[tuple[str, object]]) -> set[str]:
    """Simulate V1 DynamicChoice: Subject.objects.filter(*criteria).filter(is_active=True)."""
    qs = Subject.objects.filter(*criteria).filter(is_active=True)
    return {str(pk) for pk in qs.values_list("id", flat=True)}


# ---------------------------------------------------------------------------
# Parametrized parity tests
# ---------------------------------------------------------------------------
#
# Each entry is:
#   (test_id, v1_criteria, v2_query_template, expected_subject_keys)
#
# v1_criteria: list of (field, value) tuples passed to .filter(*criteria)
# v2_query_template: query-param string appended to the endpoint URL.
#   For cases involving subject_group UUIDs, the template contains named
#   placeholders like ``{Pumas_pt}`` that are resolved to group UUIDs at
#   test runtime (not at collection time).  Non-group cases are plain strings
#   with no placeholders and are used verbatim.
# expected_subject_keys: labels from parity_dataset subjects that should appear.

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
    # V1: groups__name=<name> (direct membership).
    # V2: subject_group=<uuid> resolved from fixture; single UUID → nested
    # expansion, but all groups are flat so nested == direct membership.
    (
        "subtype_and_group",
        [("subject_subtype", "cougar_pt"), ("groups__name", "Pumas_pt")],
        "subject_subtypes=cougar_pt&subject_group={Pumas_pt}",
        {"cougar1"},
    ),
    (
        "er_mobile_and_group",
        [("subject_subtype", "er_mobile_pt"), ("groups__name", "Subjects_pt")],
        "subject_subtypes=er_mobile_pt&subject_group={Subjects_pt}",
        {"mobile1"},
    ),
    (
        "ranger_and_group",
        [("subject_subtype", "ranger_pt"), ("groups__name", "Subjects_pt")],
        "subject_subtypes=ranger_pt&subject_group={Subjects_pt}",
        {"ranger1"},
    ),
    # --- Pattern 4: common_name_id + additional (DOT notation in v2) ---
    (
        "cn_and_additional_sex_male",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "male")],
        "common_name=black_rhino_pt&additional.sex=male",
        {"br_male"},
    ),
    (
        "cn_and_additional_sex_female",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "female")],
        "common_name=black_rhino_pt&additional.sex=female",
        {"br_female"},
    ),
    (
        "cn_and_additional_sex_unknown",
        [("common_name_id", "black_rhino_pt"), ("additional__sex", "unknown")],
        "common_name=black_rhino_pt&additional.sex=unknown",
        {"br_unknown", "rhino_calf"},
    ),
    (
        "wr_and_additional_sex_male",
        [("common_name_id", "white_rhino_pt"), ("additional__sex", "male")],
        "common_name=white_rhino_pt&additional.sex=male",
        {"wr_male"},
    ),
    (
        "wr_and_additional_sex_female",
        [("common_name_id", "white_rhino_pt"), ("additional__sex", "female")],
        "common_name=white_rhino_pt&additional.sex=female",
        {"wr_female"},
    ),
    # --- Pattern 7: subject_subtype + additional (DOT notation in v2) ---
    (
        "subtype_rhino_age_calf",
        [("subject_subtype", "rhino_pt"), ("additional__age", "calf")],
        "subject_subtypes=rhino_pt&additional.age=calf",
        {"rhino_calf"},
    ),
    (
        "subtype_elephant_sex_female",
        [("subject_subtype", "elephant_pt"), ("additional__sex", "female")],
        "subject_subtypes=elephant_pt&additional.sex=female",
        {"elephant_female"},
    ),
    # --- Pattern 8: groups__name alone ---
    (
        "group_name_only",
        [("groups__name", "DCS_Team_pt")],
        "subject_group={DCS_Team_pt}",
        {"ranger1"},
    ),
    # --- Pattern 9: groups__name__in (multi-group) ---
    # V1: groups__name__in=["BlackRhino_pt", "WhiteRhino_pt"] (OR, no nesting).
    # V2: subject_group=<uuid1>,<uuid2> — multiple UUIDs → groups__id__in (no
    # nesting), matching v1 direct-membership semantics.
    (
        "group_name_in_multi",
        [("groups__name__in", ["BlackRhino_pt", "WhiteRhino_pt"])],
        "subject_group={BlackRhino_pt},{WhiteRhino_pt}",
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
@pytest.mark.v1_migration_parity
class TestV1V2SubjectFilterParity:
    """For each production V1 criteria pattern, confirm the V2 endpoint
    returns the same Subject IDs as the direct ORM query.

    This class is tagged ``v1_migration_parity`` and should be DELETED once
    all v1 DynamicChoice schemas have been migrated to v2 ``$ref`` schemas.
    """

    @pytest.mark.parametrize(
        "test_id, v1_criteria, v2_query_template, expected_keys",
        PARITY_CASES,
        ids=[c[0] for c in PARITY_CASES],
    )
    def test_v1_v2_parity(
        self,
        superuser_client,
        parity_dataset,
        test_id,
        v1_criteria,
        v2_query_template,
        expected_keys,
    ):
        s, groups = parity_dataset

        # Resolve group-name placeholders → UUIDs at test runtime so that
        # parametrize (which runs at collection time) can remain DB-free.
        # Non-group cases have no braces and pass through unchanged.
        group_uuids = {name: str(grp.id) for name, grp in groups.items()}
        v2_query = v2_query_template.format(**group_uuids)

        # --- V1 path: raw ORM ---
        v1_ids = _v1_orm_ids(v1_criteria)

        # --- V2 path: schemas endpoint ---
        url = reverse("schemas:subjects")
        full_url = f"{url}?{v2_query}" if v2_query else url
        response = superuser_client.get(full_url)
        assert response.status_code == 200
        v2_ids = set(response.json()["enum"])

        # --- Parity assertion ---
        # Restrict comparison to subjects from our fixture to avoid
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
@pytest.mark.v1_migration_parity
class TestIsActiveParity:
    """V1 criteria ``is_active=True`` is implicitly handled by the V2 endpoint
    which excludes inactive subjects by default (via check_to_include_inactive_subjects).
    Passing ``?include_inactive=true`` overrides this.

    This class is tagged ``v1_migration_parity`` and should be DELETED once
    all v1 DynamicChoice schemas have been migrated to v2 ``$ref`` schemas.
    """

    def test_inactive_excluded_by_default(self, superuser_client, parity_dataset):
        s, _groups = parity_dataset
        url = reverse("schemas:subjects")
        response = superuser_client.get(f"{url}?common_name=black_rhino_pt")

        assert response.status_code == 200
        consts = set(response.json()["enum"])
        assert str(s["inactive_rhino"].id) not in consts
        assert str(s["br_male"].id) in consts

    def test_inactive_included_when_requested(self, superuser_client, parity_dataset):
        s, _groups = parity_dataset
        url = reverse("schemas:subjects")
        response = superuser_client.get(f"{url}?common_name=black_rhino_pt&include_inactive=true")

        assert response.status_code == 200
        consts = set(response.json()["enum"])
        assert str(s["inactive_rhino"].id) in consts
        assert str(s["br_male"].id) in consts
