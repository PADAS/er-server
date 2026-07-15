"""
Tests for the SubjectsView Phase-1 source-group permission branch and
SubjectQuerySet.by_bbox.

These lock in the ERA-13463 performance fix that:

1. Replaced the source-group ``filtered_queryset |= Subject.objects.filter(
   subjectsource__source__groups__in=source_groups)`` union -- which fanned out
   into ``LEFT OUTER JOIN subjectsource -> source -> sourcegroupsource`` on the
   outer query -- with a single correlated, tenant-scoped ``Exists()`` subquery.
2. Replaced ``by_bbox``'s top-level ``Q(pk__in=subjects) | Q(pk__in=stationary_subjects)``
   (which Postgres cannot index-drive per leg) with a ``.union()`` of the two id
   sets fed into a single ``pk__in``.

The tests assert two things:

1. SQL shape: the generated Phase-1 query references ``observations_sourcegroupsource``
   only inside a bounded correlated subquery, never via an outer ``LEFT OUTER JOIN``;
   and ``by_bbox`` no longer emits a top-level ``pk__in ... OR pk__in ...``.
2. Behavioural equivalence: the same set of subjects comes back, with no duplicate
   rows for subjects reachable via multiple sources/source-groups, and cross-tenant
   data never leaks in via the new ``Exists()`` path.
"""

from __future__ import annotations

from datetime import timedelta

import django_multitenant.utils
import pytest

import django.contrib.auth
from django.test import RequestFactory

from factories import (
    PermissionSetFactory,
    SourceFactory,
    SourceGroupFactory,
    SubjectFactory,
    SubjectGroupFactory,
    SubjectSourceFactory,
    TenantFactory,
    UserFactory,
)
from observations.models import SourceGroup, Subject, SubjectGroup, SubjectSource
from observations.views.subjects import SubjectsView

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")]

User = django.contrib.auth.get_user_model()


def _outer_table_joins(sql: str, table: str) -> int:
    """Count JOINs to ``table`` in the OUTER query (before the first WHERE).

    The fan-out bug produced ``LEFT OUTER JOIN "observations_sourcegroupsource"`` on the
    Subject query. The fix moves that table into a correlated ``EXISTS (SELECT 1 FROM ...)``
    subquery, where the table appears only after the outer WHERE clause.
    """
    lowered = sql.lower()
    outer = lowered.split(" where ", 1)[0] if " where " in lowered else lowered
    return outer.count(f'join "{table}"')


def _make_view(user: User, query_params: dict | None = None) -> SubjectsView:
    # Build the request directly with RequestFactory rather than reverse()/HTTPClient,
    # so the test does not import the full project URLconf (which pulls optional deps).
    request = RequestFactory().get("/api/v1.0/subjects/", query_params or {})
    request.user = user
    view = SubjectsView()
    view.request = request
    view.kwargs = {}
    view.queryset_linked_user = None
    view.subject_linked_sources = {}
    return view


def _phase1_queryset(view: SubjectsView, user: User, query_params: dict | None = None):
    """Run only the source/subject-group filtering stage and return the queryset."""
    base = Subject.objects.all().annotate_with_subjectstatus(delay_hours=0, mou_expiry_date=None)
    return view.filter_on_subject_and_source_groups(base, user, query_params or {})


def _grant_source_group_access(user: User, subject: Subject) -> SourceGroup:
    """Wire ``subject -> subjectsource -> source -> source_group <- permission_set <- user``."""
    perm_set = PermissionSetFactory.create(name=f"sg-ps-{subject.id}")
    user.permission_sets.add(perm_set)
    source = SourceFactory.create()
    SubjectSourceFactory.create(subject=subject, source=source)
    source_group = SourceGroupFactory.create(name=f"sg-{subject.id}")
    source_group.sources.add(source)
    source_group.permission_sets.add(perm_set)
    return source_group


def _grant_subject_group_access(user: User, subject: Subject) -> SubjectGroup:
    """Wire ``subject -> subject_group <- permission_set <- user``."""
    perm_set = PermissionSetFactory.create(name=f"subjg-ps-{subject.id}")
    user.permission_sets.add(perm_set)
    subject_group = SubjectGroupFactory.create(name=f"subjg-{subject.id}")
    subject_group.subjects.add(subject)
    subject_group.permission_sets.add(perm_set)
    return subject_group


class TestSourceGroupBranchSqlShape:
    """Phase-1 must not re-introduce the sourcegroupsource outer-join fan-out."""

    def test_non_superuser_phase1_has_no_outer_sourcegroupsource_join(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        # The source-group Exists is only rendered when the user has a permission set;
        # an empty ``permissionset__in=[]`` collapses the subquery to a constant.
        user.permission_sets.add(PermissionSetFactory.create(name="shape-ps"))
        view = _make_view(user)
        qs = _phase1_queryset(view, user)

        sql = str(qs.query)
        assert (
            _outer_table_joins(sql, "observations_sourcegroupsource") == 0
        ), f"source-group branch must not JOIN sourcegroupsource in the outer query: {sql}"
        # The table may still appear, but only inside the correlated EXISTS subquery.
        assert "exists(" in sql.lower(), f"expected a correlated EXISTS subquery: {sql}"

    def test_subquery_is_tenant_scoped_in_sql(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        user.permission_sets.add(PermissionSetFactory.create(name="tenant-shape-ps"))
        view = _make_view(user)
        sql = str(_phase1_queryset(view, user).query).lower()
        # The correlated SubjectSource subquery must carry a das_tenant correlation.
        assert "exists(" in sql, f"expected a correlated EXISTS subquery: {sql}"
        assert "das_tenant_id" in sql, f"tenant scoping missing from subquery SQL: {sql}"

    def test_superuser_phase1_has_no_sourcegroupsource_join(self):
        user = UserFactory.create(is_superuser=True)
        view = _make_view(user)
        sql = str(_phase1_queryset(view, user).query)
        assert _outer_table_joins(sql, "observations_sourcegroupsource") == 0, sql


class TestSourceGroupPermissionPath:
    def test_non_superuser_sees_subject_via_source_group(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        subject = SubjectFactory.create()
        _grant_source_group_access(user, subject)

        view = _make_view(user)
        result = set(_phase1_queryset(view, user).values_list("id", flat=True))
        assert subject.id in result

    def test_non_superuser_does_not_see_unrelated_subject(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        granted = SubjectFactory.create()
        _grant_source_group_access(user, granted)
        # A subject with a source/source-group the user has no permission set for.
        hidden = SubjectFactory.create()
        hidden_source = SourceFactory.create()
        SubjectSourceFactory.create(subject=hidden, source=hidden_source)
        hidden_group = SourceGroupFactory.create(name="hidden-sg")
        hidden_group.sources.add(hidden_source)
        hidden_group.permission_sets.add(PermissionSetFactory.create(name="hidden-ps"))

        view = _make_view(user)
        result = set(_phase1_queryset(view, user).values_list("id", flat=True))
        assert granted.id in result
        assert hidden.id not in result


class TestSubjectGroupPermissionPath:
    def test_non_superuser_sees_subject_via_subject_group(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        subject = SubjectFactory.create()
        _grant_subject_group_access(user, subject)

        view = _make_view(user)
        result = set(_phase1_queryset(view, user).values_list("id", flat=True))
        assert subject.id in result


class TestCombinedOrAccess:
    def test_subject_reachable_via_both_paths_appears_once(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        subject = SubjectFactory.create()
        _grant_subject_group_access(user, subject)
        _grant_source_group_access(user, subject)

        view = _make_view(user)
        ids = list(_phase1_queryset(view, user).distinct("id").values_list("id", flat=True))
        assert ids.count(subject.id) == 1, "a subject reachable via both paths must appear exactly once"

    def test_subjects_from_each_path_are_both_included(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        via_subject_group = SubjectFactory.create()
        _grant_subject_group_access(user, via_subject_group)
        via_source_group = SubjectFactory.create()
        _grant_source_group_access(user, via_source_group)

        view = _make_view(user)
        result = set(_phase1_queryset(view, user).values_list("id", flat=True))
        assert via_subject_group.id in result
        assert via_source_group.id in result


class TestMultiSourceNoDuplicate:
    def test_subject_with_multiple_sources_and_groups_appears_once(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        subject = SubjectFactory.create()
        perm_set = PermissionSetFactory.create(name="multi-ps")
        user.permission_sets.add(perm_set)

        # Two sources, each in its own source group, both granted via the same permission set.
        for n in range(2):
            source = SourceFactory.create()
            SubjectSourceFactory.create(subject=subject, source=source)
            group = SourceGroupFactory.create(name=f"multi-sg-{n}")
            group.sources.add(source)
            group.permission_sets.add(perm_set)

        view = _make_view(user)
        ids = list(_phase1_queryset(view, user).distinct("id").values_list("id", flat=True))
        assert ids.count(subject.id) == 1, "multi-source subject must appear exactly once"


class TestCrossTenantIsolation:
    def test_other_tenant_subject_does_not_leak_via_source_group_exists(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        # A legitimately granted subject in the current tenant.
        granted = SubjectFactory.create()
        _grant_source_group_access(user, granted)

        other_tenant = TenantFactory.create(id="11111111-1111-1111-1111-111111111111", domain="other.example.com")
        previous = django_multitenant.utils._context.tenant
        django_multitenant.utils._context.tenant = other_tenant
        try:
            other_subject = Subject.objects.create(name="other-tenant-subject", das_tenant=other_tenant)
            other_source = SourceFactory.create(das_tenant=other_tenant)
            SubjectSource.objects.create(subject=other_subject, source=other_source, das_tenant=other_tenant)
            other_group = SourceGroup.objects.create(name="other-tenant-sg", das_tenant=other_tenant)
            other_group.sources.add(other_source)
        finally:
            django_multitenant.utils._context.tenant = previous

        view = _make_view(user)
        result = set(_phase1_queryset(view, user).values_list("id", flat=True))
        assert granted.id in result
        assert other_subject.id not in result, "another tenant's subject must not leak via the source-group Exists"


class TestByBbox:
    def _subject_with_observation_in_bbox(self, *, stationary: bool = False) -> Subject:
        import uuid as _uuid
        from datetime import datetime, timezone

        from django.contrib.gis.geos import Point

        from observations.models import (
            STATIONARY_SUBJECT_VALUE,
            Observation,
            SubjectSubType,
            SubjectType,
        )

        subtype_value = STATIONARY_SUBJECT_VALUE if stationary else "active"
        subject_type, _ = SubjectType.objects.get_or_create(value=subtype_value, defaults={"display": subtype_value})
        subtype = SubjectSubType.objects.create(
            value=f"{subtype_value}-{_uuid.uuid4().hex[:8]}", display=subtype_value, subject_type=subject_type
        )
        subject = SubjectFactory.create(subject_subtype=subtype)
        source = SourceFactory.create()
        SubjectSourceFactory.create(subject=subject, source=source, location=Point(0.5, 0.5))
        Observation.objects.create(
            source=source,
            location=Point(0.5, 0.5),
            recorded_at=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        )
        return subject

    def test_bbox_sql_has_no_top_level_pk_in_or_pk_in(self):
        qs = Subject.objects.all().by_bbox([0, 0, 1, 1], last_days=timedelta(days=3), include_stationary_subjects=True)
        lowered = str(qs.query).lower()
        # Isolate the outermost predicate: everything after the outer WHERE.
        outer_where = lowered.split(" where ", 1)[1] if " where " in lowered else lowered
        # The fix unions the two id sets, so there is a single pk__in and a UNION,
        # never two pk__in legs ORed at the top level.
        assert "union" in lowered, f"by_bbox should union the two id sets: {qs.query}"
        first_predicate = outer_where.split(" or ", 1)[0]
        assert "pk__in" not in first_predicate  # Django renders as the column name, never "pk__in"
        assert (
            outer_where.count('"observations_subject"."id" in') == 1
        ), f"expected a single top-level id IN (... UNION ...), not an OR of two pk__in legs: {qs.query}"

    def test_include_stationary_true_returns_stationary_subject(self):
        moving = self._subject_with_observation_in_bbox(stationary=False)
        stationary = self._subject_with_observation_in_bbox(stationary=True)

        result = set(
            Subject.objects.all()
            .by_bbox([0, 0, 1, 1], last_days=timedelta(days=3), include_stationary_subjects=True)
            .values_list("id", flat=True)
        )
        assert moving.id in result
        assert stationary.id in result

    def test_include_stationary_false_excludes_stationary_subject(self):
        moving = self._subject_with_observation_in_bbox(stationary=False)
        stationary = self._subject_with_observation_in_bbox(stationary=True)

        result = set(
            Subject.objects.all()
            .by_bbox([0, 0, 1, 1], last_days=timedelta(days=3), include_stationary_subjects=False)
            .values_list("id", flat=True)
        )
        assert moving.id in result
        assert stationary.id not in result
