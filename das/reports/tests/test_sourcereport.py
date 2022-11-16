import random
from datetime import datetime, timedelta

import pytest
import pytz

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.core import mail
from django.core.management import call_command
from django.test import TestCase

from accounts.models import PermissionSet
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
)
from reports.distribution import (
    SOURCE_REPORT_PERMISSION_CODENAME,
    get_users_for_permission,
)
from reports.subjectsourcereport import generate_user_reports
from reports.tasks import subjectsource_report_for_tenant
from utils.tenant import get_tenant_settings

User = get_user_model()


def generate_random_positions(
    source,
    x=37.5,
    y=0.56,
    time_length=timedelta(days=1),
    start_time=None,
    interval=timedelta(minutes=60),
):
    start_time = start_time or datetime.now(tz=pytz.utc) - time_length

    recorded_at = start_time
    end_time = start_time + time_length

    while recorded_at <= end_time:
        yield Observation(source=source, recorded_at=recorded_at, location=Point(x, y), additional={})
        x += (random.random() - 0.5) / 10000
        y += (random.random() - 0.5) / 10000
        recorded_at += interval


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectSourceReport(TestCase):
    def setUp(self):
        super().setUp()
        call_command("loaddata_with_tenant", "initial_groups")

        # Setup Users

        self.u1 = User.objects.create(
            username="user1",
            first_name="User 1",
            last_name="Report User",
            email="u1@tempuri.org",
            password="Sko2901!kd219",
        )
        self.u2 = User.objects.create(
            username="user2",
            first_name="User 2",
            last_name="Report User",
            email="u2@tempuri.org",
            password="Sko2901!kd219",
        )
        self.u3 = User.objects.create(
            username="user3",
            first_name="User 3",
            last_name="Report User",
            email="u3@tempuri.org",
            password="Sko2901!kd219",
        )
        self.u4 = User.objects.create(
            username="user4",
            first_name="User 4",
            last_name="Report User",
            email="u4@tempuri.org",
            is_active=False,
            password=make_password("Sko2901!kd219"),
        )

        # Add the users to the report recipients permission set.
        pset = PermissionSet.objects.get(permissions__codename=SOURCE_REPORT_PERMISSION_CODENAME)
        for u in (self.u1, self.u2, self.u4):
            u.permission_sets.add(pset)

        # Add Subjects
        self.subject1 = Subject.objects.create(
            name="subject 1", subject_subtype_id="elephant", additional=dict(region="Region 1", species="elephant")
        )
        self.subject2 = Subject.objects.create(
            name="subject 2", subject_subtype_id="elephant", additional=dict(region="Region 2", species="elephant")
        )

        provider = SourceProvider.objects.create(provider_key="dummy", display_name="Dummy provider")
        # Add Source
        source1 = Source.objects.create(manufacturer_id="source1", provider=provider)
        source2 = Source.objects.create(manufacturer_id="source2", provider=provider)

        # Add Subject Source
        ss1 = SubjectSource.objects.create(
            subject=self.subject1, source=source1, assigned_range=(datetime.min, datetime.max)
        )
        ss2 = SubjectSource.objects.create(
            subject=self.subject2, source=source2, assigned_range=(datetime.min, datetime.max)
        )

        # Add SubjectGroup
        sg1 = SubjectGroup.objects.create(name="SG 1")
        sg2 = SubjectGroup.objects.create(name="SG 2")

        sg1.subjects.add(self.subject1)
        sg1.subjects.add(self.subject2)
        sg2.subjects.add(self.subject1)

        # Add Permission Set to Subject Group

        standard_view_permissionset = PermissionSet.objects.get(name="View Subjects")

        ps1 = PermissionSet.objects.create(name="view subject group 1")
        for p in standard_view_permissionset.permissions.all():
            ps1.permissions.add(p)

        ps2 = PermissionSet.objects.create(name="view subject group 2")
        for p in standard_view_permissionset.permissions.all():
            ps2.permissions.add(p)

        sg1.permission_sets.add(ps1)
        sg2.permission_sets.add(ps2)

        self.u1.permission_sets.add(ps1)
        self.u2.permission_sets.add(ps2)

        # Generate some observations for each source
        for observation in generate_random_positions(
            source1, start_time=datetime.now(tz=pytz.utc) - timedelta(hours=80)
        ):
            observation.save()

        for observation in generate_random_positions(
            source2, start_time=datetime.now(tz=pytz.utc) - timedelta(hours=25)
        ):
            observation.save()

    def test_report_permission(self):
        ps = Permission.objects.filter(codename=SOURCE_REPORT_PERMISSION_CODENAME)
        self.assertIsNotNone(ps)

    def _lists_equal(self, l1, l2):
        return all(x in l1 for x in l2) and all(x in l2 for x in l1)

    def test_subject_lists_per_user(self):
        """
        Make several assertions about the output of the report generator.
        """
        recipients = get_users_for_permission(SOURCE_REPORT_PERMISSION_CODENAME)
        recipients = list(recipients)

        expecting_usernames = (self.u1.username, self.u2.username)
        # Assert the list of recipients is accurate.
        self.assertTrue(self._lists_equal(list((x.username for x in recipients)), expecting_usernames))

        username_accumulator = []
        for user, context in generate_user_reports(recipients):
            username_accumulator.append(user.username)
            # Assert each report is for a user we expect.
            self.assertTrue(
                user.id in (self.u1.id, self.u2.id), "User %s should not be included in the output." % (user,)
            )

            if user.username == self.u1.username:
                self.assertTrue(len(context["groups"]) == 2)

                regions = [x["region"] for x in context["groups"]]

                # Assert the regions for User 1 are valid
                self.assertTrue(self._lists_equal(regions, ("Region 1", "Region 2")))

            if user.username == self.u2.username:
                self.assertTrue(len(context["groups"]) == 1)
                regions = [x["region"] for x in context["groups"]]
                self.assertTrue(self._lists_equal(regions, ("Region 1",)))

        self.assertTrue(
            self._lists_equal(expecting_usernames, username_accumulator),
            "The list of reported users is not equal to the expected list."
            " Expected list: {}, Actual list: {}".format(expecting_usernames, username_accumulator),
        )

    def test_source_report_rendering_and_sending(self):
        tenant_settings = get_tenant_settings()
        usernames = (self.u1.username,)
        subjectsource_report_for_tenant(usernames=usernames, domain=tenant_settings.domain)

        email = mail.outbox[0]

        assert tenant_settings.domain in email.subject
