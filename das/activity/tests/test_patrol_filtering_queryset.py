"""
Tests for PatrolFilteringQuerySet and PatrolsView._filter_by_viewable_subjects.

These lock in the ERA performance fix that replaced the chained
``.filter(patrol_segment__...)`` joins (which fanned out into T4-T8 self-joins
plus a ``.distinct()`` that made the pagination count query explode) with
correlated ``Exists()`` subqueries against PatrolSegment.

The tests assert two things:

1. SQL shape: the generated query references ``activity_patrolsegment`` only
   through bounded correlated subqueries, never via repeated aliased joins, and
   no longer applies ``DISTINCT``.
2. Behavioural equivalence: the same set of patrols comes back, with no duplicate
   rows for multi-segment patrols, and cross-tenant data never leaks in.
"""

import re
from datetime import datetime, timedelta, timezone

import django_multitenant.utils
import pytest
from psycopg2.extras import DateTimeTZRange

import django.contrib.auth
from django.db import connection
from django.db.models import Exists, OuterRef
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activity.models import (
    PC_CANCELLED,
    PC_DONE,
    PC_OPEN,
    Patrol,
    PatrolSegment,
    StateFilters,
)
from activity.views import PatrolsView
from client_http import HTTPClient
from factories import (
    PatrolFactory,
    PatrolNoteFactory,
    PatrolSegmentFactory,
    PatrolTypeFactory,
    SubjectFactory,
    TenantFactory,
    UserFactory,
)
from observations.models import Subject

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")]

User = django.contrib.auth.get_user_model()

# The fixed UUID that TenantFactory / das_tenant_monkeypatch use for the shared test tenant.
TEST_TENANT_ID = "c0973be2-8e11-4cb8-8463-897fb96391d0"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _range(start: datetime | None, end: datetime | None) -> DateTimeTZRange:
    return DateTimeTZRange(start, end)


def _outer_patrolsegment_joins(sql: str) -> int:
    """Count JOINs to activity_patrolsegment in the OUTER query (the fan-out bug).

    The bug produced ``LEFT OUTER JOIN "activity_patrolsegment" T4`` (and T5, T6, ...)
    on the Patrol query, then ``DISTINCT`` to dedupe the cartesian product. The fix
    moves patrol_segment into correlated ``EXISTS (SELECT 1 FROM activity_patrolsegment ...)``
    subqueries, where the table appears in a FROM, never a JOIN.

    We only care about ``join "activity_patrolsegment"`` -- joins to patrol_type /
    content_type *inside* a subquery are bounded and harmless.
    """
    return sql.lower().count('join "activity_patrolsegment"')


def _patrolsegment_references(sql: str) -> int:
    """How many times activity_patrolsegment is referenced at all.

    With the fix, each segment-based predicate is a single correlated subquery, so a
    handful of references (one per Exists) is expected -- but never the dozens that
    the T4-T8 join fan-out plus DISTINCT produced."""
    return sql.lower().count("activity_patrolsegment")


class TestPatrolFilteringSqlShape:
    """The query must not re-introduce patrol_segment self-joins or DISTINCT."""

    def test_by_state_emits_no_patrolsegment_joins_and_no_distinct(self):
        qs = Patrol.objects.all().by_state(
            [
                StateFilters.scheduled.value,
                StateFilters.active.value,
                StateFilters.overdue.value,
                PC_DONE,
                PC_CANCELLED,
            ]
        )
        sql = str(qs.query)
        assert _outer_patrolsegment_joins(sql) == 0, f"by_state must not JOIN patrol_segment: {sql}"
        assert "distinct" not in sql.lower(), f"by_state must not use DISTINCT: {sql}"
        # 3 segment-based states (scheduled/active/overdue) -> 3 correlated subqueries.
        assert _patrolsegment_references(sql) == 3, f"unexpected patrol_segment fan-out: {sql}"

    def test_by_date_range_overlap_emits_no_patrolsegment_joins(self):
        now = _now()
        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(days=1)).isoformat(), "upper": (now + timedelta(days=1)).isoformat()},
            patrols_overlap_daterange=True,
        )
        sql = str(qs.query)
        assert _outer_patrolsegment_joins(sql) == 0, f"by_date_range overlap must not JOIN patrol_segment: {sql}"
        assert "distinct" not in sql.lower()

    def test_by_date_range_non_overlap_emits_no_patrolsegment_joins(self):
        now = _now()
        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(days=1)).isoformat(), "upper": (now + timedelta(days=1)).isoformat()},
            patrols_overlap_daterange=False,
        )
        sql = str(qs.query)
        assert _outer_patrolsegment_joins(sql) == 0
        assert "distinct" not in sql.lower()
        assert _patrolsegment_references(sql) == 1, f"non-overlap should use a single subquery: {sql}"

    def test_by_patrol_filter_text_emits_no_patrolsegment_joins(self):
        qs = Patrol.objects.all().by_patrol_filter({"text": "ranger", "patrol_type": [], "tracked_by": []})
        sql = str(qs.query)
        assert _outer_patrolsegment_joins(sql) == 0, f"by_patrol_filter text must not JOIN patrol_segment: {sql}"
        assert "distinct" not in sql.lower()
        # One Exists for the segment text match (note match hits activity_patrolnote, not segment).
        assert _patrolsegment_references(sql) == 1, f"text filter should use a single segment subquery: {sql}"

    def test_full_list_query_has_no_patrolsegment_join_fanout(self):
        """The paginated count query is what used to run for hours. Drive the real
        endpoint and prove that none of the executed queries JOINs patrol_segment or
        uses DISTINCT, and that patrol_segment only appears via bounded correlated
        subqueries (never the T4-T8 join fan-out)."""
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        request = client.factory.get(
            reverse("patrols"),
            {"status": StateFilters.active.value, "exclude_empty_patrols": "true"},
        )
        client.force_authenticate(request, client.app_user)

        with CaptureQueriesContext(connection) as ctx:
            response = PatrolsView.as_view()(request)
        assert response.status_code == 200, response.data

        patrol_queries = [q["sql"] for q in ctx.captured_queries if "activity_patrol" in q["sql"].lower()]
        assert patrol_queries, "expected at least one patrol query to be captured"

        for sql in patrol_queries:
            lowered = sql.lower()
            assert (
                _outer_patrolsegment_joins(lowered) == 0
            ), f"patrol_segment must not appear as a JOIN in the list query: {sql}"
            # The patrol-level DISTINCT (used to dedupe the join fan-out) must be gone.
            # An unrelated `DISTINCT ON (...)` inside the viewable-subjects subquery is fine,
            # so only inspect the outer SELECT projection (before the first FROM).
            outer_projection = lowered.split(" from ", 1)[0]
            assert "distinct" not in outer_projection, f"outer query must not use DISTINCT: {sql}"

        # The count query is the historical hot spot. Confirm it does not fan out.
        count_queries = [s for s in patrol_queries if "count(" in s.lower()]
        assert count_queries, "expected a COUNT query from pagination"
        for sql in count_queries:
            assert _outer_patrolsegment_joins(sql.lower()) == 0
            assert (
                _patrolsegment_references(sql.lower()) <= 5
            ), f"too many patrol_segment references in count query, possible fan-out regression: {sql}"


class TestByState:
    def _open_patrol_with_segment(self, **segment_kwargs) -> Patrol:
        patrol = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=patrol, **segment_kwargs)
        return patrol

    def test_scheduled_returns_future_open_patrols(self):
        now = _now()
        scheduled = self._open_patrol_with_segment(scheduled_start=now + timedelta(hours=2))
        self._open_patrol_with_segment(scheduled_start=now - timedelta(hours=2))  # not scheduled

        result = set(Patrol.objects.all().by_state([StateFilters.scheduled.value]).values_list("id", flat=True))
        assert result == {scheduled.id}

    def test_active_returns_started_open_patrols(self):
        now = _now()
        active = self._open_patrol_with_segment(time_range=_range(now - timedelta(hours=1), None))
        self._open_patrol_with_segment(time_range=_range(now + timedelta(hours=1), None))  # future start

        result = set(Patrol.objects.all().by_state([StateFilters.active.value]).values_list("id", flat=True))
        assert result == {active.id}

    def test_overdue_returns_open_patrols_past_scheduled_start_without_started_range(self):
        now = _now()
        overdue = self._open_patrol_with_segment(scheduled_start=now - timedelta(hours=1))
        # has a started time_range -> not overdue
        self._open_patrol_with_segment(
            scheduled_start=now - timedelta(hours=1), time_range=_range(now - timedelta(minutes=5), None)
        )

        result = set(Patrol.objects.all().by_state([StateFilters.overdue.value]).values_list("id", flat=True))
        assert result == {overdue.id}

    def test_done_returns_done_patrols(self):
        done = PatrolFactory.create(state=PC_DONE)
        PatrolSegmentFactory.create(patrol=done)
        PatrolFactory.create(state=PC_OPEN)

        result = set(Patrol.objects.all().by_state([PC_DONE]).values_list("id", flat=True))
        assert result == {done.id}

    def test_cancelled_returns_cancelled_patrols(self):
        cancelled = PatrolFactory.create(state=PC_CANCELLED)
        PatrolSegmentFactory.create(patrol=cancelled)
        PatrolFactory.create(state=PC_OPEN)

        result = set(Patrol.objects.all().by_state([PC_CANCELLED]).values_list("id", flat=True))
        assert result == {cancelled.id}

    def test_multiple_states_union(self):
        done = PatrolFactory.create(state=PC_DONE)
        PatrolSegmentFactory.create(patrol=done)
        cancelled = PatrolFactory.create(state=PC_CANCELLED)
        PatrolSegmentFactory.create(patrol=cancelled)
        PatrolFactory.create(state=PC_OPEN)  # not requested

        result = set(Patrol.objects.all().by_state([PC_DONE, PC_CANCELLED]).values_list("id", flat=True))
        assert result == {done.id, cancelled.id}

    def test_multi_segment_patrol_is_not_duplicated(self):
        now = _now()
        active = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=active, time_range=_range(now - timedelta(hours=2), None))
        PatrolSegmentFactory.create(patrol=active, time_range=_range(now - timedelta(hours=1), None))

        ids = list(Patrol.objects.all().by_state([StateFilters.active.value]).values_list("id", flat=True))
        assert ids == [active.id], "multi-segment patrol must appear exactly once without DISTINCT"


class TestByDateRange:
    def test_overlap_matches_patrol_overlapping_window(self):
        now = _now()
        inside = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(
            patrol=inside, time_range=_range(now - timedelta(hours=1), now + timedelta(hours=1))
        )
        outside = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=outside, time_range=_range(now + timedelta(days=5), now + timedelta(days=6)))

        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(hours=2)).isoformat(), "upper": (now + timedelta(hours=2)).isoformat()},
            patrols_overlap_daterange=True,
        )
        result = set(qs.values_list("id", flat=True))
        assert inside.id in result
        assert outside.id not in result

    def test_overlap_includes_patrol_cancelled_within_window(self):
        """A cancelled patrol is included only when its cancellation revision falls in
        the window (the q2 branch). Factory creation records the cancel revision at
        ``now``, so a window around now must include it."""
        now = _now()
        cancelled = PatrolFactory.create(state=PC_CANCELLED)
        PatrolSegmentFactory.create(
            patrol=cancelled, time_range=_range(now - timedelta(hours=1), now + timedelta(hours=1))
        )

        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(hours=2)).isoformat(), "upper": (now + timedelta(hours=2)).isoformat()},
            patrols_overlap_daterange=True,
        )
        assert cancelled.id in set(qs.values_list("id", flat=True))

    def test_overlap_excludes_cancelled_patrol_outside_window(self):
        """A cancelled patrol whose segment does not overlap and whose cancellation
        revision is outside the window is excluded."""
        now = _now()
        cancelled = PatrolFactory.create(state=PC_CANCELLED)
        PatrolSegmentFactory.create(
            patrol=cancelled, time_range=_range(now + timedelta(days=10), now + timedelta(days=11))
        )

        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(days=5)).isoformat(), "upper": (now - timedelta(days=4)).isoformat()},
            patrols_overlap_daterange=True,
        )
        assert cancelled.id not in set(qs.values_list("id", flat=True))

    def test_non_overlap_matches_patrol_starting_in_window(self):
        now = _now()
        starting = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=starting, scheduled_start=now + timedelta(hours=1))
        before = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=before, scheduled_start=now - timedelta(days=5))

        qs = Patrol.objects.all().by_date_range(
            {"lower": now.isoformat(), "upper": (now + timedelta(hours=2)).isoformat()},
            patrols_overlap_daterange=False,
        )
        result = set(qs.values_list("id", flat=True))
        assert starting.id in result
        assert before.id not in result

    def test_multi_segment_patrol_not_duplicated_in_overlap(self):
        now = _now()
        patrol = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=patrol, time_range=_range(now - timedelta(hours=1), now))
        PatrolSegmentFactory.create(patrol=patrol, time_range=_range(now, now + timedelta(hours=1)))

        qs = Patrol.objects.all().by_date_range(
            {"lower": (now - timedelta(hours=2)).isoformat(), "upper": (now + timedelta(hours=2)).isoformat()},
            patrols_overlap_daterange=True,
        )
        ids = list(qs.values_list("id", flat=True))
        assert ids.count(patrol.id) == 1


class TestByPatrolFilterText:
    def test_text_matches_patrol_type_display(self):
        ptype = PatrolTypeFactory.create(display="Elephant Sweep", value="elephant-sweep")
        patrol = PatrolFactory.create(title="zzz")
        PatrolSegmentFactory.create(patrol=patrol, patrol_type=ptype)
        other = PatrolFactory.create(title="zzz")
        PatrolSegmentFactory.create(patrol=other)

        qs = Patrol.objects.all().by_patrol_filter({"text": "Elephant"})
        result = set(qs.values_list("id", flat=True))
        assert patrol.id in result
        assert other.id not in result

    def test_text_matches_note(self):
        patrol = PatrolFactory.create(title="zzz")
        PatrolSegmentFactory.create(patrol=patrol)
        PatrolNoteFactory.create(patrol=patrol, text="Rhino spotted near river")
        other = PatrolFactory.create(title="zzz")
        PatrolSegmentFactory.create(patrol=other)

        qs = Patrol.objects.all().by_patrol_filter({"text": "Rhino"})
        result = set(qs.values_list("id", flat=True))
        assert patrol.id in result
        assert other.id not in result

    def test_text_matches_title(self):
        patrol = PatrolFactory.create(title="Northern Boundary")
        PatrolSegmentFactory.create(patrol=patrol)
        other = PatrolFactory.create(title="Southern Boundary")
        PatrolSegmentFactory.create(patrol=other)

        qs = Patrol.objects.all().by_patrol_filter({"text": "Northern"})
        result = set(qs.values_list("id", flat=True))
        assert patrol.id in result
        assert other.id not in result

    def test_patrol_type_filter(self):
        ptype = PatrolTypeFactory.create()
        patrol = PatrolFactory.create()
        PatrolSegmentFactory.create(patrol=patrol, patrol_type=ptype)
        other = PatrolFactory.create()
        PatrolSegmentFactory.create(patrol=other)

        qs = Patrol.objects.all().by_patrol_filter({"patrol_type": [str(ptype.id)]})
        result = set(qs.values_list("id", flat=True))
        assert patrol.id in result
        assert other.id not in result

    def test_tracked_by_filter(self):
        subject = SubjectFactory.create()
        patrol = PatrolFactory.create()
        seg = PatrolSegmentFactory.create(patrol=patrol)
        seg.leader = subject
        seg.save()
        other = PatrolFactory.create()
        PatrolSegmentFactory.create(patrol=other)

        qs = Patrol.objects.all().by_patrol_filter({"tracked_by": [str(subject.id)]})
        result = set(qs.values_list("id", flat=True))
        assert patrol.id in result
        assert other.id not in result

    def test_multi_segment_patrol_not_duplicated_in_text_filter(self):
        ptype = PatrolTypeFactory.create(display="Buffalo Watch", value="buffalo-watch")
        patrol = PatrolFactory.create(title="zzz")
        PatrolSegmentFactory.create(patrol=patrol, patrol_type=ptype)
        PatrolSegmentFactory.create(patrol=patrol, patrol_type=ptype)

        qs = Patrol.objects.all().by_patrol_filter({"text": "Buffalo"})
        ids = list(qs.values_list("id", flat=True))
        assert ids.count(patrol.id) == 1


class TestFilterByViewableSubjects:
    def _make_view(self, user) -> PatrolsView:
        client = HTTPClient()
        request = client.factory.get(reverse("patrols"))
        request.user = user
        view = PatrolsView()
        view.request = request
        view.kwargs = {}
        return view

    def test_patrol_with_null_leader_segment_is_viewable(self):
        user = UserFactory.create(is_superuser=True)
        patrol = PatrolFactory.create()
        PatrolSegmentFactory.create(patrol=patrol, leader_id=None, leader_content_type=None)

        view = self._make_view(user)
        result = set(view._filter_by_viewable_subjects(Patrol.objects.all()).values_list("id", flat=True))
        assert patrol.id in result

    def test_patrol_with_viewable_subject_leader_is_viewable(self):
        user = UserFactory.create(is_superuser=True)
        subject = SubjectFactory.create()
        patrol = PatrolFactory.create()
        seg = PatrolSegmentFactory.create(patrol=patrol)
        seg.leader = subject
        seg.save()

        view = self._make_view(user)
        result = set(view._filter_by_viewable_subjects(Patrol.objects.all()).values_list("id", flat=True))
        assert patrol.id in result

    def test_patrol_with_user_leader_is_viewable(self):
        user = UserFactory.create(is_superuser=True)
        leader_user = UserFactory.create()
        patrol = PatrolFactory.create()
        seg = PatrolSegmentFactory.create(patrol=patrol)
        seg.leader = leader_user
        seg.save()

        view = self._make_view(user)
        result = set(view._filter_by_viewable_subjects(Patrol.objects.all()).values_list("id", flat=True))
        assert patrol.id in result

    def test_patrol_with_non_viewable_subject_leader_is_excluded(self):
        user = UserFactory.create(is_superuser=False, is_staff=True)
        # A subject the user cannot view (no subject group / permission set linkage).
        hidden_subject = SubjectFactory.create()
        patrol = PatrolFactory.create()
        seg = PatrolSegmentFactory.create(patrol=patrol)
        seg.leader = hidden_subject
        seg.save()

        viewable_ids = set(Subject.objects.by_user_subjects_and_linked(user).values_list("id", flat=True))
        view = self._make_view(user)
        result = set(view._filter_by_viewable_subjects(Patrol.objects.all()).values_list("id", flat=True))
        if hidden_subject.id not in viewable_ids:
            assert patrol.id not in result

    def test_multi_segment_patrol_not_duplicated(self):
        user = UserFactory.create(is_superuser=True)
        patrol = PatrolFactory.create()
        PatrolSegmentFactory.create(patrol=patrol, leader_id=None, leader_content_type=None)
        PatrolSegmentFactory.create(patrol=patrol, leader_id=None, leader_content_type=None)

        view = self._make_view(user)
        ids = list(view._filter_by_viewable_subjects(Patrol.objects.all()).values_list("id", flat=True))
        assert ids.count(patrol.id) == 1


class TestSortPatrols:
    def test_sort_order_open_before_done_before_cancelled(self):
        open_p = PatrolFactory.create(state=PC_OPEN, title="bbb")
        PatrolSegmentFactory.create(patrol=open_p)
        done_p = PatrolFactory.create(state=PC_DONE, title="aaa")
        PatrolSegmentFactory.create(patrol=done_p)
        cancelled_p = PatrolFactory.create(state=PC_CANCELLED, title="aaa")
        PatrolSegmentFactory.create(patrol=cancelled_p)

        ordered = list(Patrol.objects.all().sort_patrols().values_list("id", flat=True))
        assert ordered.index(open_p.id) < ordered.index(done_p.id)
        assert ordered.index(done_p.id) < ordered.index(cancelled_p.id)

    def test_sort_by_title_within_same_state(self):
        a = PatrolFactory.create(state=PC_OPEN, title="Alpha")
        PatrolSegmentFactory.create(patrol=a)
        c = PatrolFactory.create(state=PC_OPEN, title="Charlie")
        PatrolSegmentFactory.create(patrol=c)
        b = PatrolFactory.create(state=PC_OPEN, title="Bravo")
        PatrolSegmentFactory.create(patrol=b)

        ordered = list(Patrol.objects.all().sort_patrols().values_list("id", flat=True))
        assert ordered.index(a.id) < ordered.index(b.id) < ordered.index(c.id)

    def test_multi_segment_patrol_appears_once_after_sort(self):
        patrol = PatrolFactory.create(state=PC_OPEN, title="Gamma")
        PatrolSegmentFactory.create(patrol=patrol)
        PatrolSegmentFactory.create(patrol=patrol)

        ids = list(Patrol.objects.all().sort_patrols().values_list("id", flat=True))
        assert ids.count(patrol.id) == 1


class TestCrossTenantIsolation:
    def test_other_tenant_patrol_does_not_leak_into_current_tenant_query(self):
        now = _now()
        other_tenant = TenantFactory.create(id="11111111-1111-1111-1111-111111111111", domain="other.example.com")

        # Build a fully active patrol+segment owned by the OTHER tenant. The
        # das_tenant_monkeypatch fixture pins the current tenant via this mocked
        # _context, so we flip it for the duration of the cross-tenant setup.
        previous = django_multitenant.utils._context.tenant
        django_multitenant.utils._context.tenant = other_tenant
        try:
            other_patrol = Patrol.objects.create(state=PC_OPEN, das_tenant=other_tenant, title="Other tenant patrol")
            PatrolSegment.objects.create(
                patrol=other_patrol,
                das_tenant=other_tenant,
                time_range=_range(now - timedelta(hours=1), None),
            )
        finally:
            django_multitenant.utils._context.tenant = previous

        # And one active patrol owned by the current test tenant.
        current_patrol = PatrolFactory.create(state=PC_OPEN)
        PatrolSegmentFactory.create(patrol=current_patrol, time_range=_range(now - timedelta(hours=1), None))

        result = set(Patrol.objects.all().by_state([StateFilters.active.value]).values_list("id", flat=True))
        assert current_patrol.id in result
        assert other_patrol.id not in result, "another tenant's patrol must not leak into the current tenant query"

    def test_subquery_is_tenant_scoped_in_sql(self):
        qs = Patrol.objects.all().by_state([StateFilters.active.value])
        sql = str(qs.query).lower()
        # The correlated PatrolSegment subquery should carry a das_tenant filter.
        assert 'v0."das_tenant_id"' in sql or "das_tenant_id" in sql, f"tenant scoping missing from subquery SQL: {sql}"


def _aliased_patrolsegment_self_joins(sql: str) -> int:
    """Count the *aliased* (Tn) activity_patrolsegment joins in the OUTER query.

    Each chained ``.filter(patrol_segment__...)`` on a multi-valued relation forces
    Django to emit a separate join to activity_patrolsegment. The first reuses the bare
    table name; every subsequent one gets a fresh alias (T4, T5, T6, ...). So K chained
    filters produce ``_outer_patrolsegment_joins == K`` total joins, of which ``K - 1``
    are the aliased self-joins counted here -- the unmistakable signature of the fan-out.
    """
    return len(set(re.findall(r'join\s+"activity_patrolsegment"\s+(t\d+)', sql.lower())))


class TestPatrolSegmentJoinExplosion:
    """Quantify the row explosion the pre-fix chained-join pattern produced.

    The old code expressed each segment predicate as an independent
    ``Patrol.objects.filter(patrol_segment__...=...)`` call. Because ``patrol_segment``
    is a multi-valued (reverse FK) relation, Django cannot fold those filters into one
    join -- it emits a fresh ``LEFT OUTER JOIN activity_patrolsegment Tn`` per call.

    For a single patrol with N segments and K such chained filters where every segment
    satisfies every predicate, each join multiplies the row set fully: the intermediate
    (pre-``DISTINCT``) result for that one patrol contains **N ** K** rows. With N=10 and
    K=4 that is 10,000 rows -- for a single patrol. A ``.distinct()`` collapses it back to
    one row, but the planner must still materialise (and the COUNT(*) for pagination must
    still scan) the full cartesian product first. That is the cost the ``Exists()`` rewrite
    eliminated: a correlated EXISTS short-circuits at the first matching segment, so the
    patrol is emitted exactly once with no join fan-out and no DISTINCT.

    These tests are deterministic row-count / SQL-shape assertions, never timing.
    """

    N_SEGMENTS = 10

    def _patrol_with_n_segments(self, n: int) -> Patrol:
        patrol = PatrolFactory.create(state=PC_OPEN)
        for _ in range(n):
            # No predicate set -> every segment trivially satisfies the
            # "...isnull=False" filters used below, so every join multiplies fully.
            PatrolSegmentFactory.create(patrol=patrol)
        return patrol

    @pytest.mark.parametrize(
        "num_filters, expected_rows",
        [
            (2, 100),  # 10 ** 2
            (4, 10_000),  # 10 ** 4
        ],
    )
    def test_chained_filters_fan_out_to_n_to_the_k_rows(self, num_filters: int, expected_rows: int):
        """K chained .filter(patrol_segment__...) calls fan one N-segment patrol into N**K rows."""
        self._patrol_with_n_segments(self.N_SEGMENTS)

        # Mimic the pre-fix pattern: K *independent* .filter() calls on the multi-valued
        # patrol_segment relation, each one a predicate that all N segments satisfy.
        # Using distinct field lookups (id / patrol_id / das_tenant_id / created_at) keeps
        # each filter its own join alias rather than being merged.
        predicates = [
            {"patrol_segment__id__isnull": False},
            {"patrol_segment__patrol_id__isnull": False},
            {"patrol_segment__das_tenant_id__isnull": False},
            {"patrol_segment__created_at__isnull": False},
        ]
        qs = Patrol.objects.all()
        for predicate in predicates[:num_filters]:
            qs = qs.filter(**predicate)

        assert self.N_SEGMENTS**num_filters == expected_rows  # self-documenting N**K

        # Pre-DISTINCT: the single patrol fans out into N**K rows.
        assert (
            qs.values("id").count() == expected_rows
        ), f"expected {self.N_SEGMENTS}**{num_filters} == {expected_rows} fan-out rows for one patrol"
        # DISTINCT collapses the cartesian product back to the one real patrol.
        assert qs.distinct().count() == 1

        # And the SQL proves K separate joins to activity_patrolsegment (1 bare + K-1 Tn).
        sql = str(qs.query)
        assert (
            _outer_patrolsegment_joins(sql) == num_filters
        ), f"expected {num_filters} patrol_segment joins (the fan-out) in: {sql}"
        assert (
            _aliased_patrolsegment_self_joins(sql) == num_filters - 1
        ), f"expected {num_filters - 1} aliased (Tn) patrol_segment self-joins in: {sql}"

    def test_exists_path_returns_patrol_once_with_no_join_fan_out(self):
        """The Exists() rewrite expresses the same intent with one correlated subquery:
        the N-segment patrol comes back exactly once, with no DISTINCT and no Tn self-join."""
        patrol = self._patrol_with_n_segments(self.N_SEGMENTS)

        qs = Patrol.objects.filter(
            Exists(
                PatrolSegment.objects.filter(
                    patrol=OuterRef("pk"),
                    id__isnull=False,
                )
            )
        )

        # Exactly one row, with no .distinct() applied.
        ids = list(qs.values_list("id", flat=True))
        assert ids == [patrol.id], "Exists() path must yield the patrol exactly once without DISTINCT"
        assert qs.count() == 1

        sql = str(qs.query)
        # The bug signature -- aliased self-joins to patrol_segment in the OUTER query -- is gone.
        assert _outer_patrolsegment_joins(sql) == 0, f"Exists() path must not JOIN patrol_segment: {sql}"
        assert _aliased_patrolsegment_self_joins(sql) == 0, f"Exists() path must not emit T4/T5-style self-joins: {sql}"
        assert "distinct" not in sql.lower(), f"Exists() path must not need DISTINCT: {sql}"
        # patrol_segment appears only inside the single correlated EXISTS subquery.
        assert _patrolsegment_references(sql) == 1, f"expected a single bounded EXISTS reference: {sql}"

    def test_chained_join_and_exists_agree_on_the_result(self):
        """Behavioural equivalence: old fan-out (deduped) and new Exists() select the same patrol."""
        patrol = self._patrol_with_n_segments(self.N_SEGMENTS)

        chained = (
            Patrol.objects.all()
            .filter(patrol_segment__id__isnull=False)
            .filter(patrol_segment__patrol_id__isnull=False)
            .distinct()
        )
        exists = Patrol.objects.filter(Exists(PatrolSegment.objects.filter(patrol=OuterRef("pk"), id__isnull=False)))

        assert set(chained.values_list("id", flat=True)) == {patrol.id}
        assert set(exists.values_list("id", flat=True)) == {patrol.id}
