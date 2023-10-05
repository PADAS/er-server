from datetime import datetime, timedelta

import pytest
import pytz
from pytz import UTC

from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.db.models import F
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PermissionSet, User
from observations.models import (
    Observation,
    Source,
    Subject,
    SubjectGroup,
    SubjectMaximumSpeed,
    SubjectSource,
    SubjectStatus,
    escape_provider_name,
)


def make_perm(perm):
    return "{0}.{1}".format(perm.content_type.app_label, perm.codename)


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SubjectGroupTestCase(TestCase):
    def setUp(self):
        all_set = PermissionSet.objects.create(name="all")
        some_set = PermissionSet.objects.create(name="some")

        some_set.parent = all_set
        some_set.save()

    def test_subject_in_group(self):
        ele = Subject.objects.create_subject(name="ele", additional={})
        ele_group = SubjectGroup.objects.create(name="ele_group")

        ele.groups.add(ele_group)

        ele = Subject.objects.get(name="ele")
        self.assertIn(ele_group, ele.groups.all())


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SubjectPermissionsTestCase(TestCase):
    user_const = dict(last_name="last", first_name="first")

    def setUp(self):
        self.all_set = PermissionSet.objects.create(name="all")
        self.some_set = PermissionSet.objects.create(name="some")
        self.view_last_position_name = "view_last_position"

        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.some_set.parent = self.all_set
        self.some_set.permissions.add(Permission.objects.get(codename=self.view_last_position_name))
        self.some_set.save()

        self.superuser = User.objects.create_superuser("admin", "admin@test.com", "admin", **self.user_const)
        self.user = User.objects.create_user("joe", "joe@example.com", "joe", **self.user_const)

    def test_user_has_view_permission(self):
        user = User.objects.create_user(
            username="active_user",
            email="active_user@test.com",
            password=User.objects.make_random_password(),
            **self.user_const,
        )

        user.permission_sets.add(self.some_set)

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name="ele_group")
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertTrue(user.has_perm(make_perm(self.view_last_position), ele))


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectQuerySet:
    def test_get_queyset_by_linked_user(self, user, subject):
        user.linked_subject = subject
        user.save()

        subject_queryset = Subject.objects.by_linked_user(user)

        assert subject_queryset.count() == 1
        assert subject_queryset.first() == subject


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SubjectAlertTestCase(TestCase):
    user_const = dict(last_name="last", first_name="first")

    def setUp(self):
        self.all_set = PermissionSet.objects.create(name="all")
        self.some_set = PermissionSet.objects.create(name="some")

        self.some_set.parent = self.all_set
        self.some_set.save()

    def test_return_user(self):
        user = User.objects.create_user(
            username="active_user",
            email="active_user@test.com",
            password=User.objects.make_random_password(),
            **self.user_const,
        )
        user.permission_sets.add(self.some_set)
        user.permission_sets.add(self.all_set)
        user.save()

        user2 = User.objects.create_user(
            username="no_alert",
            email="active@test.com",
            password=User.objects.make_random_password(),
            **self.user_const,
        )

        ele = Subject.objects.create_subject(name="ele", additional={})

        ele_group = SubjectGroup.objects.create(name="ele_group")
        ele.groups.add(ele_group)

        ele_group.permission_sets.add(self.some_set)

        self.assertIn(user, ele.get_users_to_notify())
        self.assertNotIn(user2, ele.get_users_to_notify())

    def test_permission_with_proxy_content_type_created(self):
        """
        A proxy model's permissions use its own content type rather than the
        content type of the concrete model.
        """
        opts = SubjectMaximumSpeed._meta
        codename = get_permission_codename("add", opts)
        self.assertTrue(
            Permission.objects.filter(
                content_type__model=opts.model_name,
                content_type__app_label=opts.app_label,
                codename=codename,
            ).exists()
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationManager:
    OBSERVATION_POINTS = [
        (-103.64398956298828, 20.612540918310213),
        (0, 0),
        (-103.57738494873045, 20.70313296563719),
        (0, 0),
        (-103.50425720214844, 20.639531429485633),
    ]
    EMPTY_OBSERVATION_POINTS = [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0)]

    @pytest.mark.parametrize("include_empty_location", [False, True])
    def test_get_latest_observation_source_with_bunch_of_observations(self, subject_source, include_empty_location):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        latest_observation_id = None
        for count, point in enumerate(self.OBSERVATION_POINTS, 1):
            observation = Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )
            if count == 1:
                latest_observation_id = observation.id

        observation = Observation.objects.get_latest_observation_source(
            source, include_empty_location=include_empty_location
        )

        assert latest_observation_id == observation.id

        if include_empty_location:
            observation = LatestObservationSource.objects.get(source=source).observation
            assert latest_observation_id == observation.id

    def test_get_latest_observation_source_with_all_empty_observations_include_empty_observations(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        latest_observation_id = None
        for count, point in enumerate(self.EMPTY_OBSERVATION_POINTS, 1):
            observation = Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )
            if count == 1:
                latest_observation_id = observation.id

        observation = Observation.objects.get_latest_observation_source(source, include_empty_location=True)
        assert latest_observation_id == observation.id

        observation = LatestObservationSource.objects.get(source=source).observation
        assert latest_observation_id == observation.id

    def test_get_latest_observation_source_with_all_empty_observations_not_include_empty_observations(
        self, subject_source
    ):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        for count, point in enumerate(self.EMPTY_OBSERVATION_POINTS, 1):
            Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(point),
                source=source,
            )

        observation = Observation.objects.get_latest_observation_source(source, include_empty_location=False)
        assert observation is None

    def test_get_latest_observation_source_with_latest_flagged_as_excluded(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)
        latest_observation = Observation.objects.create(
            recorded_at=now - timedelta(minutes=5), location=Point(self.OBSERVATION_POINTS[0]), source=source
        )
        flagged_observation = Observation.objects.create(
            recorded_at=now, location=Point(self.OBSERVATION_POINTS[0]), source=source
        )

        observation = Observation.objects.get_latest_observation_source(source, include_empty_location=True)
        assert observation is not None
        assert observation.id == flagged_observation.id

        observation = LatestObservationSource.objects.get(source=source).observation
        assert observation.id == flagged_observation.id

        flagged_observation.exclusion_flags = Observation.EXCLUDED_MANUALLY
        flagged_observation.save()
        flagged_observation.refresh_from_db()

        observation = Observation.objects.get_latest_observation_source(source, include_empty_location=True)
        assert observation.id == latest_observation.id
        observation = LatestObservationSource.objects.get(source=source).observation
        assert observation.id == latest_observation.id


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationTriggers:
    def test_source_last_observation_relation_without_observation(self, subject_source):
        source = subject_source.source

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )

        assert not sources.first().last_observation
        assert not sources.first().last_observation_recorded_at

    def test_insert_a_new_observation(self, subject_source):
        source = subject_source.source

        observation = Observation.objects.create(
            source=source,
            location=Point(0, 0),
            recorded_at=datetime.now(tz=UTC),
        )
        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )

        assert sources.first().last_observation == observation.id
        assert sources.first().last_observation_recorded_at == observation.recorded_at

    def test_insert_a_observation_with_previous_observations_in_source(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=UTC)
        for item in range(1, 4):
            Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )

        observation = Observation.objects.create(
            source=source,
            location=Point(0, 0),
            recorded_at=now,
        )

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )

        assert sources.first().last_observation == observation.id
        assert sources.first().last_observation_recorded_at == observation.recorded_at

    def test_edit_not_the_latest_observation_and_do_it_the_latest(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=UTC)
        middle_observation_id = None
        for item in range(1, 5):
            tmp_observation = Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )
            if item == 3:
                middle_observation_id = tmp_observation.id

        observation = Observation.objects.get(id=middle_observation_id)
        observation.recorded_at = now
        observation.save()

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )

        assert sources.first().last_observation == observation.id
        assert sources.first().last_observation_recorded_at == observation.recorded_at

    def test_edit_latest_observation_and_keep_it_the_latest(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=UTC)
        for item in range(1, 5):
            Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )

        observations = Observation.objects.all().order_by("-recorded_at")
        observation = observations.first()
        observation.recorded_at = now
        observation.save()

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )
        assert sources.first().last_observation == observations[0].id
        assert sources.first().last_observation_recorded_at == now

    def test_exclude_latest_observation_for_source(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=UTC)
        for item in range(1, 5):
            Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )

        observations = list(Observation.objects.all().order_by("-recorded_at"))
        observation = observations[0]
        observation.exclusion_flags = Observation.EXCLUDED_MANUALLY
        observation.save()

        last_observation = LatestObservationSource.objects.get_latest_for_source(source, include_empty_location=True)
        assert last_observation.id == observations[1].id

    def test_delete_not_latest_observation(self, subject_source):
        source = subject_source.source

        now = datetime.now(tz=UTC)
        middle_observation_id = None
        for item in range(1, 5):
            tmp_observation = Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )
            if item == 3:
                middle_observation_id = tmp_observation.id

        Observation.objects.get(id=middle_observation_id).delete()

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )
        observation = Observation.objects.all().order_by("-recorded_at").first()
        assert sources.first().last_observation == observation.id
        assert sources.first().last_observation_recorded_at == observation.recorded_at

    def test_delete_the_latest_observation(self, subject_source):
        source = subject_source.source
        now = datetime.now(tz=UTC)
        for item in range(1, 5):
            Observation.objects.create(
                source=source,
                location=Point(0, 0),
                recorded_at=now - timedelta(minutes=5 * item),
            )
        observations = Observation.objects.all().order_by("-recorded_at")
        new_latest_observation = observations[1]

        observations[0].delete()

        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )
        assert sources.first().last_observation == new_latest_observation.id
        assert sources.first().last_observation_recorded_at == new_latest_observation.recorded_at

    def test_delete_the_only_and_latest_observation(self, subject_source):
        source = subject_source.source
        observation = Observation.objects.create(
            source=source,
            location=Point(0, 0),
            recorded_at=datetime.now(tz=UTC),
        )
        observation.delete()
        sources = (
            Source.objects.filter(id__in=[source.id])
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
        )

        assert not sources.first().last_observation
        assert not sources.first().last_observation_recorded_at


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestExclusionFlagsFiltering:
    """Test cases for the unified by_exclusion_flags filtering with 3rd-party support."""

    @pytest.fixture
    def exclusion_flags_test_data(self):
        """Fixture to create test data for exclusion flags filtering tests."""
        from factories import SubjectSourceFactory

        subject_source = SubjectSourceFactory.create()
        source = subject_source.source
        now = datetime.now(tz=pytz.utc)

        # Create observations with different exclusion flag combinations
        obs_no_flags = Observation.objects.create(
            source=source, location=Point(0, 1), recorded_at=now - timedelta(minutes=10), exclusion_flags=0
        )

        obs_manual = Observation.objects.create(
            source=source,
            location=Point(1, 1),
            recorded_at=now - timedelta(minutes=9),
            exclusion_flags=Observation.EXCLUDED_MANUALLY,  # 1
        )

        obs_automatic = Observation.objects.create(
            source=source,
            location=Point(2, 1),
            recorded_at=now - timedelta(minutes=8),
            exclusion_flags=Observation.EXCLUDED_AUTOMATICALLY,  # 2
        )

        obs_both_system = Observation.objects.create(
            source=source,
            location=Point(3, 1),
            recorded_at=now - timedelta(minutes=7),
            exclusion_flags=Observation.EXCLUDED_MANUALLY | Observation.EXCLUDED_AUTOMATICALLY,  # 3
        )

        # Create observations with 3rd-party flags (upper 16 bits)
        # 3rd-party flag 1 in bit 48 = 0x0001000000000000
        obs_third_party_1 = Observation.objects.create(
            source=source,
            location=Point(4, 1),
            recorded_at=now - timedelta(minutes=6),
            exclusion_flags=0x0001000000000000,
        )

        # 3rd-party flag 2 in bit 49 = 0x0002000000000000
        obs_third_party_2 = Observation.objects.create(
            source=source,
            location=Point(5, 1),
            recorded_at=now - timedelta(minutes=5),
            exclusion_flags=0x0002000000000000,
        )

        # Combined system + 3rd-party flags
        obs_combined = Observation.objects.create(
            source=source,
            location=Point(6, 1),
            recorded_at=now - timedelta(minutes=4),
            exclusion_flags=Observation.EXCLUDED_MANUALLY | 0x0001000000000000,
        )

        # Multiple 3rd-party flags
        obs_multi_third_party = Observation.objects.create(
            source=source,
            location=Point(7, 1),
            recorded_at=now - timedelta(minutes=3),
            exclusion_flags=0x0003000000000000,  # Both 3rd-party flags
        )

        obs_third_party_ncz = Observation.objects.create(
            source=source,
            location=Point(8, 1),
            recorded_at=now - timedelta(minutes=2),
            exclusion_flags=1311673391471656960,
        )

        return {
            "source": source,
            "obs_no_flags": obs_no_flags,
            "obs_manual": obs_manual,
            "obs_automatic": obs_automatic,
            "obs_both_system": obs_both_system,
            "obs_third_party_1": obs_third_party_1,
            "obs_third_party_2": obs_third_party_2,
            "obs_combined": obs_combined,
            "obs_multi_third_party": obs_multi_third_party,
            "obs_third_party_ncz": obs_third_party_ncz,
        }

    def test_filter_flag_none_returns_all_observations(self, exclusion_flags_test_data):
        """When filter_flag is None (e.g., 'null'), all observations should be returned."""
        source = exclusion_flags_test_data["source"]
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=None)
        assert queryset.count() == 9

    def test_filter_flag_zero_uses_system_only_filtering(self, exclusion_flags_test_data):
        """When filter_flag is 0, should only filter by system flags (exclude manual/auto)."""
        source = exclusion_flags_test_data["source"]
        obs_no_flags = exclusion_flags_test_data["obs_no_flags"]
        obs_third_party_1 = exclusion_flags_test_data["obs_third_party_1"]
        obs_third_party_2 = exclusion_flags_test_data["obs_third_party_2"]
        obs_multi_third_party = exclusion_flags_test_data["obs_multi_third_party"]
        obs_third_party_ncz = exclusion_flags_test_data["obs_third_party_ncz"]

        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0)
        # Should return observations with flag 0 and 3rd-party flags only
        expected_ids = {
            obs_no_flags.id,
            obs_third_party_1.id,
            obs_third_party_2.id,
            obs_multi_third_party.id,
            obs_third_party_ncz.id,
        }
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

    def test_filter_system_flags_preserves_third_party_flags(self, exclusion_flags_test_data):
        """System flag filtering should preserve observations with only 3rd-party flags."""
        source = exclusion_flags_test_data["source"]
        obs_manual = exclusion_flags_test_data["obs_manual"]
        obs_automatic = exclusion_flags_test_data["obs_automatic"]
        obs_both_system = exclusion_flags_test_data["obs_both_system"]
        obs_combined = exclusion_flags_test_data["obs_combined"]

        # Filter for manually excluded (flag 1) - should include obs with flags 1 and 3 (1|2) and combined
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=1)
        expected_ids = {obs_manual.id, obs_both_system.id, obs_combined.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

        # Filter for automatically excluded (flag 2) - should include obs with flags 2 and 3 (1|2)
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=2)
        expected_ids = {obs_automatic.id, obs_both_system.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

        # Filter for both system flags (flag 3) - should include any obs with either flag 1 or 2 set
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=3)
        expected_ids = {obs_manual.id, obs_automatic.id, obs_both_system.id, obs_combined.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

    def test_filter_third_party_flags_uses_full_filtering(self, exclusion_flags_test_data):
        """When filter_flag contains 3rd-party bits, should use full 64-bit filtering."""
        source = exclusion_flags_test_data["source"]
        obs_third_party_1 = exclusion_flags_test_data["obs_third_party_1"]
        obs_third_party_2 = exclusion_flags_test_data["obs_third_party_2"]
        obs_combined = exclusion_flags_test_data["obs_combined"]
        obs_multi_third_party = exclusion_flags_test_data["obs_multi_third_party"]
        obs_third_party_ncz = exclusion_flags_test_data["obs_third_party_ncz"]

        # Filter for 3rd-party flag 1 only
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0x0001000000000000)
        expected_ids = {obs_third_party_1.id, obs_combined.id, obs_multi_third_party.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

        # Filter for 3rd-party flag 2 only
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0x0002000000000000)
        expected_ids = {obs_third_party_2.id, obs_multi_third_party.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

        # Filter for both 3rd-party flags
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0x0003000000000000)
        expected_ids = {obs_third_party_1.id, obs_third_party_2.id, obs_combined.id, obs_multi_third_party.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

        # Filter for NCZ flag
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0x1000000000000000)
        expected_ids = {obs_third_party_ncz.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

    def test_filter_combined_system_and_third_party_flags(self, exclusion_flags_test_data):
        """Test filtering with both system and 3rd-party flags set."""
        source = exclusion_flags_test_data["source"]
        obs_manual = exclusion_flags_test_data["obs_manual"]
        obs_both_system = exclusion_flags_test_data["obs_both_system"]
        obs_combined = exclusion_flags_test_data["obs_combined"]
        obs_third_party_1 = exclusion_flags_test_data["obs_third_party_1"]
        obs_multi_third_party = exclusion_flags_test_data["obs_multi_third_party"]

        # Filter for manual exclusion + 3rd-party flag 1
        # This should match observations that have BOTH flags set
        combined_flag = Observation.EXCLUDED_MANUALLY | 0x0001000000000000
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=combined_flag)

        # When filtering with combined flags, we get observations that have ANY of the specified bits set
        # So this should include: obs_manual (has flag 1), obs_both_system (has flag 1),
        # obs_combined (has both), obs_third_party_1 (has 3rd party flag),
        # obs_multi_third_party (has 3rd party flag)
        expected_ids = {
            obs_manual.id,
            obs_both_system.id,
            obs_combined.id,
            obs_third_party_1.id,
            obs_multi_third_party.id,
        }
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

    def test_filter_boundary_values(self, exclusion_flags_test_data):
        """Test filtering at the boundary between system and 3rd-party flags."""
        source = exclusion_flags_test_data["source"]
        obs_third_party_1 = exclusion_flags_test_data["obs_third_party_1"]
        obs_combined = exclusion_flags_test_data["obs_combined"]
        obs_multi_third_party = exclusion_flags_test_data["obs_multi_third_party"]

        # Maximum system flag value (all lower 48 bits set)
        max_system_flag = 0x0000FFFFFFFFFFFF
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=max_system_flag)
        # Should use system-only filtering, so observations with only 3rd-party flags are preserved
        assert queryset.count() > 0

        # Minimum 3rd-party flag value (bit 48 set)
        min_third_party_flag = 0x0001000000000000
        queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=min_third_party_flag)
        # Should use full filtering
        expected_ids = {obs_third_party_1.id, obs_combined.id, obs_multi_third_party.id}
        actual_ids = set(queryset.values_list("id", flat=True))
        assert actual_ids == expected_ids

    def test_include_empty_location_parameter(self, exclusion_flags_test_data):
        """Test that include_empty_location parameter works with all filtering modes."""
        source = exclusion_flags_test_data["source"]
        now = datetime.now(tz=pytz.utc)

        # Create observation at (0,0)
        empty_obs = Observation.objects.create(
            source=source, location=Point(0, 0), recorded_at=now - timedelta(minutes=1), exclusion_flags=0
        )

        try:
            # Test with include_empty_location=False (default)
            queryset = Observation.objects.filter(source=source).by_exclusion_flags(filter_flag=0)
            assert empty_obs.id not in queryset.values_list("id", flat=True)

            # Test with include_empty_location=True
            queryset = Observation.objects.filter(source=source).by_exclusion_flags(
                filter_flag=0, include_empty_location=True
            )
            assert empty_obs.id in queryset.values_list("id", flat=True)
        finally:
            empty_obs.delete()

    def test_system_flags_mask_constant(self):
        """Verify the SYSTEM_FLAGS_MASK constant is correctly defined."""
        assert Observation.SYSTEM_FLAGS_MASK == 0x0000FFFFFFFFFFFF

    def test_third_party_flags_mask_constant(self):
        """Verify the THIRD_PARTY_FLAGS_MASK constant is correctly defined."""
        assert Observation.THIRD_PARTY_FLAGS_MASK == 0xFFFF000000000000

    def test_system_and_third_party_properties(self, exclusion_flags_test_data):
        """Test the system_exclusion_flags and third_party_exclusion_flags properties."""
        obs_manual = exclusion_flags_test_data["obs_manual"]
        obs_third_party_1 = exclusion_flags_test_data["obs_third_party_1"]
        obs_combined = exclusion_flags_test_data["obs_combined"]

        # Test observation with only system flags
        assert obs_manual.system_exclusion_flags == 1
        assert obs_manual.third_party_exclusion_flags == 0

        # Test observation with only 3rd-party flags
        assert obs_third_party_1.system_exclusion_flags == 0
        assert obs_third_party_1.third_party_exclusion_flags == 1

        # Test observation with combined flags
        assert obs_combined.system_exclusion_flags == 1
        assert obs_combined.third_party_exclusion_flags == 1


class TestObservationQuerySet(TestCase):
    """Test ObservationQuerySet methods."""

    def test_get_subject_observations_partitioned_avoid_unions(self):
        """Test that avoid_unions parameter works correctly."""
        # Create test data
        subject = Subject.objects.create(name="Test Subject")
        source = Source.objects.create(provider_id=1)

        # Create subject-source assignment
        now = timezone.now()
        SubjectSource.objects.create(
            subject=subject, source=source, assigned_range=(now - timedelta(days=1), now + timedelta(days=1))
        )

        # Create some observations
        for i in range(3):
            Observation.objects.create(source=source, recorded_at=now + timedelta(hours=i), location="POINT(1.0 1.0)")

        # Test with avoid_unions=True
        queryset_with_avoid = Observation.objects.get_subject_observations_partitioned(subject, avoid_unions=True)

        # Test with avoid_unions=False (default)
        queryset_without_avoid = Observation.objects.get_subject_observations_partitioned(subject, avoid_unions=False)

        # Both should return the same number of observations
        self.assertEqual(queryset_with_avoid.count(), 3)
        self.assertEqual(queryset_without_avoid.count(), 3)

        # The queryset with avoid_unions should not have UNION operations
        # We can check this by looking at the SQL
        sql_with_avoid = str(queryset_with_avoid.query)

        # The avoid_unions version should not contain UNION
        self.assertNotIn("UNION", sql_with_avoid.upper())

    def test_get_subject_observations_partitioned_no_source_assignments(self):
        """Test that method returns empty QuerySet when no source assignments exist."""
        present_time = timezone.now()

        # Create an expired source assignment
        subject_1 = Subject.objects.create(name="Test Subject 1")
        source_1 = Source.objects.create(provider_id=1)
        SubjectSource.objects.create(
            subject=subject_1,
            source=source_1,
            assigned_range=(present_time - timedelta(days=10), present_time - timedelta(days=1)),
        )

        # Create an active source assignment for a second subject
        subject_2 = Subject.objects.create(name="Test Subject 2")
        source_2 = Source.objects.create(provider_id=2)
        SubjectSource.objects.create(
            subject=subject_2,
            source=source_2,
            assigned_range=(present_time - timedelta(days=10), present_time + timedelta(days=1)),
        )

        Observation.objects.create(
            source=source_2, recorded_at=present_time - timedelta(hours=1), location="POINT(1.0 1.0)"
        )

        # Test with avoid_unions=True (the path that returns self.none())
        queryset = Observation.objects.get_subject_observations_partitioned(
            subject_1, avoid_unions=True, since=present_time - timedelta(hours=12)
        )

        # Should return empty QuerySet
        self.assertEqual(queryset.count(), 0)

        # Test with avoid_unions=False (default behavior)
        queryset_default = Observation.objects.get_subject_observations_partitioned(
            subject_1, avoid_unions=False, since=present_time - timedelta(hours=12)
        )

        # Should also return empty QuerySet
        self.assertEqual(queryset_default.count(), 0)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationExclusionProcessing:

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_excluded_observation_not_update_subjectstatus(self, subject_source_with_observations):
        subject_source, observation = subject_source_with_observations
        subject = subject_source.subject

        subjectstatus = SubjectStatus.objects.get_current_status(subject)
        assert subjectstatus.location == observation.location

        # observation with invalid location, and was automatically excluded
        Observation.objects.create(
            source=subject_source.source,
            recorded_at=timezone.now(),
            location=Point(0, 0),
            exclusion_flags=Observation.EXCLUDED_AUTOMATICALLY,
        )

        subjectstatus = SubjectStatus.objects.get_current_status(subject)
        assert subjectstatus.location == observation.location


class TestEscapeProviderName:
    """Tests for escape_provider_name utility function."""

    @pytest.mark.parametrize(
        "input_name,expected_output",
        [
            # Basic cases
            ("EdgeTech", "edgetech"),
            ("edge_tech", "edge_tech"),
            ("EDGETECH", "edgetech"),
            # Spaces and special characters replaced with underscore
            ("Edge Tech", "edge_tech"),
            ("Edge-Tech", "edge_tech"),
            ("Edge.Tech", "edge_tech"),
            ("Edge Tech Inc.", "edge_tech_inc"),
            # Multiple special characters collapsed to single underscore
            ("Edge  Tech", "edge_tech"),
            ("Edge--Tech", "edge_tech"),
            ("Edge...Tech", "edge_tech"),
            ("Edge - Tech", "edge_tech"),
            # Leading/trailing special characters stripped
            (" EdgeTech ", "edgetech"),
            ("-EdgeTech-", "edgetech"),
            ("  Edge Tech  ", "edge_tech"),
            # Numbers preserved
            ("EdgeTech123", "edgetech123"),
            ("Edge2Tech", "edge2tech"),
            ("123EdgeTech", "123edgetech"),
            # Mixed cases
            ("Edge Tech (USA)", "edge_tech_usa"),
            ("Edge@Tech#Inc!", "edge_tech_inc"),
            # Empty and edge cases
            ("a", "a"),
            ("A1", "a1"),
        ],
    )
    def test_escape_provider_name(self, input_name, expected_output):
        """Test that provider names are correctly escaped to URL-safe keys."""
        assert escape_provider_name(input_name) == expected_output
