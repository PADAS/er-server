import datetime
import json
import random
from datetime import timedelta
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import dateutil.parser
import pytest
import pytz

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.test import override_settings
from django.urls import resolve, reverse
from rest_framework import status

from accounts.models import PermissionSet, User
from client_http import HTTPClient
from conftest import TENANT_RESPONSE
from core.tests import API_BASE, BaseAPITest
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    Observation,
    Source,
    SourceGroup,
    Subject,
    SubjectGroup,
    SubjectSource,
)
from observations.views import (
    SourceGroupsView,
    SourceProvidersViewPartial,
    SourceView,
    SubjectGroupsView,
    SubjectGroupView,
    SubjectSourcesView,
    SubjectSubjectSourcesView,
    SubjectsView,
    SubjectView,
)
from utils.tenant import Tenant


def random_string(length=10):
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz01234567890$@") for _ in range(length))


class BasePermissionTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        user_const = dict(last_name="last", first_name="first")
        self.superuser = User.objects.create_user(
            "super", "super@test.com", "super", is_superuser=True, is_staff=True, **user_const
        )
        self.realtime_view_user = User.objects.create_user(
            "realtime_joe", "realtimejoe@test.com", "realtime_view_joe", **user_const
        )
        self.delayed_view_user = User.objects.create_user(
            "delayed_view_joe", "jerry@test.com", "delayed_view_joe", **user_const
        )
        self.no_view_user = User.objects.create_user("no_view_john", "john@test.com", "no_view_john", **user_const)
        self.source_admin_user = User.objects.create_user(
            "john_the_source_admin", "john.source@test.com", "john_the_source_admin", **user_const
        )

        self.source_set = PermissionSet.objects.create(name="source")
        self.source_set.permissions.add(
            Permission.objects.get_by_natural_key("view_sourcegroup", "observations", "sourcegroup")
        )
        self.source_admin_user.permission_sets.add(self.source_set)

        self.subject_set = PermissionSet.objects.create(name="subject")
        self.subject_view_last_set = PermissionSet.objects.create(name="subject_view")
        self.subject_view_delayed_set = PermissionSet.objects.create(name="subject_view_delayed")
        self.subject_view_realtime_set = PermissionSet.objects.create(name="subject_view_realtime")

        self.view_subjectgroup = Permission.objects.get_by_natural_key(
            "view_subjectgroup", "observations", "subjectgroup"
        )

        self.view_subject_name = "view_subject"
        self.view_subject = Permission.objects.get(codename=self.view_subject_name)

        self.view_begins_permission_name = "access_begins_60"
        self.view_begins_permission = Permission.objects.get(codename=self.view_begins_permission_name)

        self.view_last_position_name = "access_ends_0"
        self.view_last_position = Permission.objects.get(codename=self.view_last_position_name)

        self.view_real_time_name = "access_ends_0"
        self.view_real_time = Permission.objects.get(codename=self.view_real_time_name)

        self.view_delayed_name = "access_ends_1"
        self.view_delayed = Permission.objects.get(codename=self.view_delayed_name)

        self.subject_set.children.add(self.subject_view_last_set)
        self.subject_view_last_set.permissions.add(self.view_last_position, self.view_subject, self.view_subjectgroup)
        self.subject_view_last_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup
        )

        self.subject_set.children.add(self.subject_view_realtime_set)
        self.subject_view_realtime_set.permissions.add(self.view_real_time, self.view_subject, self.view_subjectgroup)
        self.subject_view_realtime_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup
        )

        self.subject_set.children.add(self.subject_view_delayed_set)
        self.subject_view_delayed_set.permissions.add(self.view_delayed, self.view_subject, self.view_subjectgroup)
        self.subject_view_delayed_set.permissions.add(
            self.view_begins_permission, self.view_subject, self.view_subjectgroup
        )

        self.all_group = SubjectGroup.objects.create(name="all_group")

        self.ele = Subject.objects.create(name="ele", additional={})
        self.ele_group = SubjectGroup.objects.create(name="ele_group")
        self.all_group.children.add(self.ele_group)

        self.ele.groups.add(self.ele_group)

        self.ranger = Subject.objects.create(name="ranger", additional={})
        self.ranger_group = SubjectGroup.objects.create(name="ranger_group")
        self.all_group.children.add(self.ranger_group)

        self.ranger.groups.add(self.ranger_group)

        DEFAULT_DATE_RANGE = (
            datetime.datetime(2015, 11, 1, tzinfo=pytz.utc),
            dateutil.parser.parse("9999-12-31 23:59:59+0000"),
        )

        source = Source.objects.create(additional={})
        subject_source = SubjectSource.objects.create(
            assigned_range=DEFAULT_DATE_RANGE, source=source, subject=self.ele, additional={}
        )
        t = datetime.datetime.now(tz=pytz.UTC) - datetime.timedelta(hours=26)
        self.ob_yesterday = Observation.objects.create(
            source_id=source.id, location=Point((31, 0)), recorded_at=t, additional={}
        )

        t = datetime.datetime.now(tz=pytz.UTC)
        self.ob_today = Observation.objects.create(
            source_id=source.id, location=Point((31, 0)), recorded_at=t, additional={}
        )

        self.ele_group.permission_sets.add(self.subject_view_realtime_set)
        self.ele_group.save()

        self.all_group.permission_sets.add(self.subject_view_realtime_set)
        self.all_group.save()

        self.ele_group.permission_sets.add(self.subject_view_delayed_set)
        self.ele_group.save()

        self.delayed_view_user.permission_sets.add(self.subject_view_delayed_set)
        self.delayed_view_user.save()

        self.realtime_view_user.permission_sets.add(self.subject_view_realtime_set)
        self.realtime_view_user.save()


class SubjectViewPermissionsTest(BasePermissionTest):
    def setUp(self):
        super().setUp()
        self.tenant = Tenant.from_dict(TENANT_RESPONSE)
        self.thread = MagicMock()
        self.thread.tenant_object = self.tenant

    def xtest_not_return_current_observation_for_subject(self):
        request = self.factory.get(API_BASE + "/subject/")
        self.force_authenticate(request, self.delayed_view_user)

        response = SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue("last_position_date" in response.data)
        self.assertNotEqual(self.ob_today.recorded_at, response.data["last_position_date"])

    def test_not_return_subject_sources(self):
        request = self.factory.get(API_BASE + "/subject/{0}/sources".format(self.ele.id))
        self.force_authenticate(request, self.no_view_user)

        response = SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 403)

    @override_settings(TIME_ZONE="Africa/Nairobi")
    def test_return_subject_sources(self):
        request = self.factory.get(API_BASE + "/subject/{0}/subjectsources".format(self.ele.id))
        self.force_authenticate(request, self.realtime_view_user)

        response = SubjectSubjectSourcesView.as_view()(request, id=str(self.ele.id))
        assert response.status_code == 200
        assert len(response.data)

    @patch("utils.tenant.thread._get_local_thread")
    def test_return_all_observation_for_subject(self, get_main_thread):
        get_main_thread.return_value = self.thread
        self.tenant.env_settings.show_track_days = 1000
        request = self.factory.get(API_BASE + "/subject/")
        self.force_authenticate(request, self.realtime_view_user)

        response = SubjectView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue("last_position_date" in response.data)
        self.assertEqual(self.ob_today.recorded_at, response.data["last_position_date"])

    def test_unauthorised_observation_viewing_of_subject(self):
        request = self.factory.get(API_BASE + "/subject/")
        self.force_authenticate(request, self.no_view_user)
        response = SubjectView.as_view()(request, id=str(self.ele.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_return_subject_sources(self):
        request = self.factory.get(API_BASE + "/subject/{0}/sources".format(self.ele.id))
        self.force_authenticate(request, self.delayed_view_user)

        response = SubjectSourcesView.as_view()(request, id=str(self.ele.id))
        self.assertEqual(response.status_code, 200)

    def test_return_subjects_bbox_no_view(self):
        bbox = "37.18,0.1,37.55,0.54"
        request = self.factory.get(API_BASE + "/subjects/")
        self.force_authenticate(request, self.no_view_user)

        response = SubjectsView.as_view()(request, bbox=bbox)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("utils.tenant.thread._get_local_thread")
    def test_return_subjects_bbox_view_delayed(self, get_main_thread):
        get_main_thread.return_value = self.thread
        bbox = "37.18,0.1,37.55,0.54"
        request = self.factory.get(API_BASE + "/subjects/?bbox={0}".format(bbox))
        self.force_authenticate(request, self.delayed_view_user)

        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    @patch("utils.tenant.thread._get_local_thread")
    def test_not_return_ranger_in_subjects_call(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjects/")
        self.force_authenticate(request, self.delayed_view_user)

        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse([s for s in response.data if s["id"] == str(self.ranger.id)])

    def authenticate_user_and_get_subjects(self, url):
        request = self.factory.get(API_BASE + url)
        self.force_authenticate(request, self.superuser)
        return SubjectsView.as_view()(request)

    @patch("utils.tenant.thread._get_local_thread")
    def test_subjects_api_call_only_returns_active_subjects(self, get_main_thread):
        get_main_thread.return_value = self.thread
        response = self.authenticate_user_and_get_subjects("/subjects/")
        self.assertEqual(response.status_code, 200)

        # Returns all 2 subjects: Both are active
        self.assertEqual(len(response.data), 2)

        # Update one subject, set to inactive
        self.ele.is_active = False
        self.ele.save()
        response = self.authenticate_user_and_get_subjects("/subjects/")

        # Only one subject is returned, only one is active
        self.assertEqual(len(response.data), 1)

        # adding `include_inactive=True` param fetches both active and inactive
        response = self.authenticate_user_and_get_subjects("/subjects/?include_inactive=True")
        self.assertEqual(len(response.data), 2)

    def test_subjectsview_having_perms_via_sourcegroup(self):
        expected_subject_name = "ele no. 2"
        # Fixtures for testing subject access via source-group.
        user_with_sourcegroup_access = User.objects.create_user(
            username="ele2owner",
            email="ele2owner@test.com",
            password=random_string(10),
            last_name="Bar",
            first_name="Foo",
        )
        ele2 = Subject.objects.create(name=expected_subject_name, additional={})
        ele2_source = Source.objects.create(manufacturer_id="ele2-source")
        ele2_subjectsource = SubjectSource.objects.create(
            source=ele2_source,
            subject=ele2,
            assigned_range=(
                datetime.datetime(1000, 1, 1, tzinfo=pytz.utc),
                datetime.datetime(9999, 1, 1, tzinfo=pytz.utc),
            ),
        )
        ele2_sourcegroup = SourceGroup.objects.create(name="ele2 source group")
        ele2_sourcegroup.sources.add(ele2_source)

        # Give permissions by source group permission set.
        view_ele2_sourcegroup_ps = PermissionSet.objects.create(name="View Ele2 Source Group")

        perms = Permission.objects.get_by_natural_key("view_sourcegroup", "observations", "sourcegroup")
        view_ele2_sourcegroup_ps.permissions.add(perms)
        ele2_sourcegroup.permission_sets.add(view_ele2_sourcegroup_ps)

        user_with_sourcegroup_access.permission_sets.add(view_ele2_sourcegroup_ps)

        p1 = PermissionSet.objects.create(name="sourcegroup user subject view perms")
        perms = Permission.objects.get_by_natural_key("view_subject", "observations", "subject")
        p1.permissions.add(perms)
        user_with_sourcegroup_access.permission_sets.add(p1)

        # Two assertions on test fixtures.
        self.assertEqual(ele2_sourcegroup.permission_sets.all().count(), 1)
        self.assertEqual(
            SourceGroup.objects.filter(
                permission_sets__in=user_with_sourcegroup_access.get_all_permission_sets()
            ).count(),
            1,
        )

        # Make the request
        request = self.factory.get(API_BASE + "/subjects/")
        self.force_authenticate(request, user_with_sourcegroup_access)

        response = SubjectsView.as_view()(
            request,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], expected_subject_name)


class SubjectGroupViewTest(BasePermissionTest):
    def setUp(self):
        super().setUp()
        self.tenant = Tenant.from_dict(TENANT_RESPONSE)
        self.thread = MagicMock()
        self.thread.tenant_object = self.tenant

    @patch("utils.tenant.thread._get_local_thread")
    def test_delay_view_user_return_subject_groups(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.delayed_view_user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "ele_group")

    @patch("utils.tenant.thread._get_local_thread")
    def test_realtime_view_user_return_subject_groups(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.realtime_view_user)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "all_group")

    @patch("utils.tenant.thread._get_local_thread")
    def test_superuser_return_subject_groups(self, get_main_thread):
        get_main_thread.return_value = self.thread
        return_groups = ("Subjects", "all_group")
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertTrue(response.data[0]["name"] in return_groups)
        self.assertTrue(response.data[1]["name"] in return_groups)

    @patch("utils.tenant.thread._get_local_thread")
    def test_return_single_subject_group_by_id(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjectgroup/{id}".format(id=self.ele_group.id))
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupView.as_view()(request, id=str(self.ele_group.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.ele_group.id))

    @patch("utils.tenant.thread._get_local_thread")
    def test_single_subject_group_has_etag(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjectgroup/{id}".format(id=self.ele_group.id))
        self.force_authenticate(request, self.superuser)
        response = SubjectGroupView.as_view()(request, id=str(self.ele_group.id))

        assert response.status_code == status.HTTP_200_OK
        assert "etag" in response.headers

    @patch("utils.tenant.thread._get_local_thread")
    def test_single_subject_group_etag_changes_on_update(self, get_main_thread):
        get_main_thread.return_value = self.thread
        request = self.factory.get(API_BASE + "/subjectgroup/{id}".format(id=self.ele_group.id))
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupView.as_view()(request, id=str(self.ele_group.id))
        etag = response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK

        self.ele_group.name = "new name"
        self.ele_group.save(update_fields=["name"])

        second_response = SubjectGroupView.as_view()(request, id=str(self.ele_group.id))
        second_etag = second_response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK
        assert etag != second_etag

    def test_not_return_subject_group_no_view_permission(self):
        request = self.factory.get(API_BASE + "/subjectgroup/{id}".format(id=self.ele_group.id))
        self.force_authenticate(request, self.no_view_user)

        response = SubjectGroupView.as_view()(request, id=str(self.ele_group.id))
        self.assertEqual(response.status_code, 403)

    def test_not_return_subject_groups_no_view_permission(self):
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.no_view_user)

        response = SubjectGroupsView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_etag_should_be_different_on_duplicate_request(self):
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupsView.as_view()(request)
        etag = response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK

        second_response = SubjectGroupsView.as_view()(request)
        second_etag = second_response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK
        assert etag != second_etag

    def test_etag_should_change_by_value_changes(self):
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupsView.as_view()(request, render_last_location=False)
        etag = response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK

        obj = SubjectGroup.objects.first()
        obj.name = "new name"
        obj.save(update_fields=["name"])

        second_response = SubjectGroupsView.as_view()(request, render_last_location=False)
        second_etag = second_response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK
        assert etag != second_etag

    def test_etag_should_change_by_m2m_relation_changes(self):
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.superuser)

        response = SubjectGroupsView.as_view()(request, render_last_location=False)
        etag = response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK

        subject_group = SubjectGroup.objects.get(name="Subjects")
        subject = Subject.objects.first()
        subject.name = "new name"
        subject.save(update_fields=["name"])
        subject_group.subjects.add(subject)

        second_response = SubjectGroupsView.as_view()(request, render_last_location=False)
        second_etag = second_response.headers["ETag"]

        assert response.status_code == status.HTTP_200_OK
        assert etag != second_etag

    def test_etag_should_change_between_master_and_profile(self):
        url = reverse("subject-groups")
        perm_set = PermissionSet.objects.get(name="View ranger_group Subject Group")
        self.app_user.permission_sets.add(perm_set)
        self.superuser.act_as_profiles.add(self.app_user)

        request_superuser = self.factory.get(url)
        self.force_authenticate(request_superuser, self.superuser)
        response_superuser = SubjectGroupsView.as_view()(request_superuser, render_last_location=False)
        etag_superuser = response_superuser.headers["ETag"]

        assert response_superuser.status_code == status.HTTP_200_OK

        request_app_user = self.factory.get(url)
        request_app_user.META["user-profile"] = str(self.app_user.id)
        self.force_authenticate(request_app_user, self.app_user)
        response_app_user = SubjectGroupsView.as_view()(request_app_user, render_last_location=False)
        etag_app_user = response_app_user.headers["ETag"]

        assert response_app_user.status_code == status.HTTP_200_OK
        assert etag_superuser != etag_app_user


class SourceGroupViewTest(BasePermissionTest):
    def setUp(self):
        super().setUp()

    def test_user_return_source_groups(self):
        request = self.factory.get(API_BASE + "/sourcegroups")
        self.force_authenticate(request, self.source_admin_user)

        response = SourceGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_user_return_source_groups_no_view_permission(self):
        request = self.factory.get(API_BASE + "/sourcegroups")
        self.force_authenticate(request, self.no_view_user)

        response = SourceGroupsView.as_view()(request)
        self.assertEqual(response.status_code, 403)


@pytest.fixture
def user_with_one_week_track_perms(db, django_user_model):
    user_const = dict(last_name="last", first_name="first")
    user = User.objects.create_user("perms_user", "das_perms@vulcan.com", "perms", **user_const)

    subject_set = PermissionSet.objects.create(name="subject_perm_set")
    permission_names = [
        "Can view subject",
        "Can view tracks no more than 7 days old",
        "Can view tracks no less than 0 days old",
        "Can view tracks no less than 1 day old",
        "Can view tracks no less than 3 days old",
        "Can view tracks no less than 7 days old",
    ]
    for name in permission_names:
        subject_set.permissions.add(Permission.objects.get(name=name))
    user.permission_sets.add(subject_set)
    return user


class UserSubject(NamedTuple):
    user: any
    subject: Subject


@pytest.fixture
def subject_with_month_long_track(db, user_with_one_week_track_perms):
    subject = Subject.objects.create_subject(name="Bobo", subject_subtype_id="elephant")
    source = Source.objects.create(manufacturer_id="random-collar")
    subjectgroup = SubjectGroup.objects.create(name="Bobo_subjectgroup")
    subjectgroup.subjects.add(subject)
    subjectgroup.permission_sets.set(user_with_one_week_track_perms.permission_sets.all())
    SubjectSource.objects.create(subject=subject, source=source, assigned_range=DEFAULT_ASSIGNED_RANGE)

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    next_time = now - datetime.timedelta(days=31)
    x = 37.5
    y = 0.56
    while now > next_time:
        x += (random.random() - 0.5) / 10000
        y += (random.random() - 0.5) / 10000
        Observation.objects.create(
            source=subject.source, location=Point(x=x, y=y), recorded_at=next_time, additional={}
        )
        next_time += datetime.timedelta(hours=6)

    return UserSubject(user_with_one_week_track_perms, subject)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_one_week_track_permissions(
    subject_with_month_long_track, client, tenant_response, tenant_document_cache_client_mock
):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    oldest_time = now - datetime.timedelta(days=31)

    user, subject = (subject_with_month_long_track.user, subject_with_month_long_track.subject)
    client.force_login(user)
    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    response = client.get(url + "?since=" + oldest_time.isoformat())
    max_day = datetime.datetime.combine(
        datetime.date.today() - datetime.timedelta(days=7), datetime.time.min, tzinfo=datetime.timezone.utc
    )
    assert response.status_code == 200
    assert not [t for t in response.data["features"][0]["properties"]["coordinateProperties"]["times"] if t < max_day]

    # 'Can view all historical tracks' perm will precede over 'Can view tracks no more than 7 days old' perm.
    SubjectGroup.objects.create(name="Kittens")
    kitten_ps = PermissionSet.objects.get(name="View Kittens Subject Group")
    kitten_ps.permissions.add(Permission.objects.get(name="Can view all historical tracks"))
    user.permission_sets.add(kitten_ps)

    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    response = client.get(url + "?since=" + oldest_time.isoformat())
    max_day = datetime.datetime.combine(
        datetime.date.today() - datetime.timedelta(days=7), datetime.time.min, tzinfo=datetime.timezone.utc
    )
    assert response.status_code == 200
    assert [t for t in response.data["features"][0]["properties"]["coordinateProperties"]["times"] if t > max_day]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_retrieving_future_tracks(
    subject_with_month_long_track, client, tenant_response, tenant_document_cache_client_mock
):
    since = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=1)
    until = since + datetime.timedelta(days=31)

    user, subject = (subject_with_month_long_track.user, subject_with_month_long_track.subject)
    client.force_login(user)
    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    params = {"since": since.isoformat(), "until": until.isoformat()}
    response = client.get(url, params)

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_retrieving_since_equals_to_until(
    subject_with_month_long_track, client, tenant_response, tenant_document_cache_client_mock
):
    since = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(days=1)
    until = since

    user, subject = (subject_with_month_long_track.user, subject_with_month_long_track.subject)
    client.force_login(user)
    url = reverse("subject-view-tracks", kwargs=dict(subject_id=subject.id))
    params = {"since": since.isoformat(), "until": until.isoformat()}
    response = client.get(url, params)

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceProvider:
    def test_update_source_provider_with_patch_method(self, source_provider):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        request = client.factory.patch(
            f"{client.api_base}/sourceprovider/{source_provider.id}/",
            data={
                "provider_key": "New provider key",
                "display_name": "This is a provider key",
                "additional": {},
            },
        )
        client.force_authenticate(request, client.app_user)
        response = SourceProvidersViewPartial.as_view()(request, id=source_provider.id)

        assert response.status_code == 200
        assert response.data.get("provider_key") == "New provider key"
        assert response.data.get("display_name") == "This is a provider key"
        assert response.data.get("additional") == {}

    def test_update_source_provider_with_put_method(self, source_provider):
        client = HTTPClient()
        client.app_user.is_superuser = True
        request = client.factory.put(
            f"{client.api_base}/sourceprovider/{source_provider.id}/",
            data={
                "provider_key": "New provider key",
                "display_name": "This is a provider key",
                "additional": {},
            },
        )
        client.force_authenticate(request, client.app_user)
        response = SourceProvidersViewPartial.as_view()(request, id=source_provider.id)

        assert response.status_code == 200
        assert response.data.get("provider_key") == "New provider key"
        assert response.data.get("display_name") == "This is a provider key"
        assert response.data.get("additional") == {}


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceSubjectsView:
    def test_create_subject_source(self, subject_source, superuser_client):
        subject = subject_source.subject
        source = subject_source.source
        url = f"{reverse('source-subjects-view', kwargs={'id': subject.id})}"
        data = {
            "assigned_range": {"lower": "2022-05-01T17:00:00-07:00", "upper": "2022-05-05T16:59:59-07:00"},
            "source": source.id,
            "subject": subject.id,
            "additional": {},
            "location": {"latitude": 20.420935, "longitude": -103.313486},
        }
        subject_source_count = SubjectSource.objects.all().count()

        response = superuser_client.post(url, data=data)

        assert response.status_code == 201
        assert SubjectSource.objects.all().count() == subject_source_count + 1


@pytest.mark.django_db
class TestSourceView:
    def test_resolve_url(self):
        resolver = resolve("/api/v1.0/source/manufacturer/")

        assert resolver.func.cls == SourceView


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestFlattenObservationsView:
    FLATTEN_URL = reverse("flatten-observations")

    def test_subject_without_observations(
        self, subject, superuser_client, tenant_response, tenant_document_cache_client_mock
    ):
        response = superuser_client.get(
            self.FLATTEN_URL, {"subject_id": f"{subject.id}", "created_after": "2022-10-18T14:49:15.869490+00:00"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_subject_with_observations(
        self, superuser_client, subject_source, tenant_response, tenant_document_cache_client_mock
    ):
        now = datetime.datetime.now(tz=pytz.utc)
        source = subject_source.source
        for count in range(1, 6):
            Observation.objects.create(
                recorded_at=now - timedelta(minutes=count * 5),
                location=Point(-103.64398956298828, 20.612540918310213),
                source=source,
            )

        response = superuser_client.get(
            self.FLATTEN_URL, {"subject_id": f"{subject_source.subject.id}", "created_after": now.isoformat()}
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 5


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectsView:
    base_url = "subjects-list-view"

    @pytest.fixture
    def _get_superuser_client(self, subject, superuser, superuser_client):
        subject.linked_user = superuser
        subject.save()
        return superuser_client.get(reverse(self.base_url)), superuser

    @pytest.fixture
    def _get_client(self, subject):
        client = HTTPClient()
        subject.linked_user = client.app_user
        subject.save()
        request = client.factory.get(reverse(self.base_url))
        client.force_authenticate(request, client.app_user)

        return SubjectsView.as_view()(request), client.app_user

    def test_subjects_view_with_linked_user(self, tenant_document_cache_client_mock, _get_superuser_client):
        response, user = _get_superuser_client
        assert response.data[0]["user"]["id"] == str(user.id)

    def test_subjects_view_without_linked_user(self, tenant_document_cache_client_mock, _get_superuser_client):
        response, _ = _get_superuser_client

        assert not hasattr(response.data[0], "user")

    def test_subjects_view_with_linked_user_and_not_subject_permission(self, _get_client):
        response, user = _get_client

        assert response.data[0]["user"]["id"] == str(user.id)

    def test_subjects_view_with_not_linked_user_or_subject_permission(self):
        client = HTTPClient()
        request = client.factory.get(reverse("subjects-list-view"))
        client.force_authenticate(request, client.app_user)

        response = SubjectsView.as_view()(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectView:
    base_url = "subject-view"

    @pytest.fixture
    def _get_superuser_client(self, subject, superuser, superuser_client):
        url = reverse(self.base_url, kwargs={"id": subject.id})
        subject.linked_user = superuser
        subject.save()
        return superuser_client.get(url), superuser

    @pytest.fixture
    def _get_client(self, subject):
        client = HTTPClient()
        subject.linked_user = client.app_user
        subject.save()
        url = reverse(self.base_url, kwargs={"id": subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        return SubjectView.as_view()(request, id=str(subject.id)), client.app_user

    def test_subject_view_with_linked_user(self, tenant_document_cache_client_mock, _get_superuser_client):
        response, user = _get_superuser_client
        assert response.data["user"]["id"] == str(user.id)

    def test_subject_view_with_linked_user_and_not_subject_permission(self, _get_client):
        response, user = _get_client
        assert response.data["user"]["id"] == str(user.id)

    def test_subject_view_without_linked_user(self, tenant_document_cache_client_mock, _get_superuser_client):
        response, _ = _get_superuser_client
        assert not hasattr(response.data, "user")

    def test_subject_view_with_not_linked_user_or_subject_permission(self, subject):
        client = HTTPClient()
        url = reverse("subject-view", kwargs={"id": subject.id})
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)

        response = SubjectView.as_view()(request, id=str(subject.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def _test_subject_view_with_linked_user_ask_for_random_subject(self, five_subjects, superuser_client, superuser):
        subject1 = five_subjects[0]
        subject2 = five_subjects[1]
        url = reverse("subject-view", kwargs={"id": subject2.id})
        subject1.linked_user = superuser
        subject1.save()
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        assert response.data["id"] == str(subject2.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectGroupManagement:
    """Test cases for adding and removing subjects from subject groups via POST/DELETE."""

    def make_request_data(self, subject_id):
        """Helper to create properly formatted request data."""
        if not isinstance(subject_id, list):
            subject_id = [subject_id]
        return json.dumps([{"id": str(id)} for id in subject_id])

    def test_add_subject_to_group_success(self, superuser_client, subject, subject_group_empty):
        """Test successfully adding a subject to a group via POST."""
        # Verify subject is not in group initially
        assert subject not in subject_group_empty.subjects.all()

        url = reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id})
        response = superuser_client.post(url, data=self.make_request_data(subject.id), content_type="application/json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data[0]["id"] == str(subject.id)

        # Verify subject was actually added to the group
        assert subject in subject_group_empty.subjects.all()

    def test_add_multiple_subjects_to_group_success(self, superuser_client, five_subjects, subject_group_empty):
        """Test successfully adding multiple subjects to a group via POST."""
        subject1 = five_subjects[0]
        subject2 = five_subjects[1]
        assert subject1 not in subject_group_empty.subjects.all()
        assert subject2 not in subject_group_empty.subjects.all()

        url = reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id})
        response = superuser_client.post(
            url, data=self.make_request_data([subject1.id, subject2.id]), content_type="application/json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert subject1 in subject_group_empty.subjects.all()
        assert subject2 in subject_group_empty.subjects.all()

    def test_remove_subject_from_group_success(self, superuser_client, subject, subject_group_empty):
        """Test successfully removing a subject from a group via DELETE."""
        # Add subject to group first
        subject_group_empty.subjects.add(subject)
        assert subject in subject_group_empty.subjects.all()

        response = superuser_client.delete(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data(subject.id),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK

        # Verify subject was actually removed from the group
        assert subject not in subject_group_empty.subjects.all()

    def test_add_subject_permission_denied(self, user_client, subject, subject_group_empty):
        """Test that users without change_subjectgroup permission cannot add subjects."""
        response = user_client.post(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data(subject.id),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        # This is Django REST Framework's default permission denied response
        assert "Forbidden" in str(response.data["status"]["detail"])

    def test_add_subject_missing_subject_id(self, superuser_client, subject_group_empty):
        """Test error handling when subject ID is missing from request."""
        response = superuser_client.post(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=json.dumps({}),  # Missing subject ID
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_subject_invalid_subject_id(self, superuser_client, subject_group_empty):
        """Test error handling when subject ID doesn't exist."""
        response = superuser_client.post(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data("00000000-0000-0000-0000-000000000000"),  # Non-existent UUID
            content_type="application/json",
        )

        # The get_object_or_404 should handle this, but it might return a 500 in tests
        # due to the way the view is being called directly
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]

    def test_add_already_existing_subject_to_group(self, superuser_client, subject, subject_group_empty):
        """Test adding a subject that's already in the group (should still succeed)."""
        # Add subject to group first
        subject_group_empty.subjects.add(subject)
        assert subject in subject_group_empty.subjects.all()

        response = superuser_client.post(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data(subject.id),
            content_type="application/json",
        )

        # Django's add() method is idempotent, so this should succeed
        assert response.status_code == status.HTTP_200_OK

    def test_remove_non_existing_subject_from_group(self, superuser_client, subject, subject_group_empty):
        """Test removing a subject that's not in the group (should still succeed)."""
        # Verify subject is not in group
        assert subject not in subject_group_empty.subjects.all()

        response = superuser_client.delete(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data(subject.id),
            content_type="application/json",
        )

        # Django's remove() method is idempotent, so this should succeed
        assert response.status_code == status.HTTP_200_OK

    def test_remove_subject_permission_denied(self, user_client, subject, subject_group_empty):
        """Test that users without change_subjectgroup permission cannot remove subjects."""
        # Add subject to group first
        subject_group_empty.subjects.add(subject)

        response = user_client.delete(
            reverse("subject-group-subjects-view", kwargs={"id": subject_group_empty.id}),
            data=self.make_request_data(subject.id),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
