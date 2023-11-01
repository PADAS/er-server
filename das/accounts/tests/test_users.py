import uuid

import pytest
from faker import Faker

from django.forms import ValidationError

from accounts.models import User

faker = Faker()


@pytest.mark.django_db
class TestUserTenant:
    def test_create_users_diff_tenant_with_same_email(self, five_tenants):
        same_email = "same@email.com"

        for tenant in five_tenants:
            user = User.objects.create(
                username=faker.profile()["username"],
                password="password",
                email=same_email,
                das_tenant=tenant,
            )
            assert uuid.UUID(tenant.id) == user.das_tenant.id
            assert same_email == user.email

        assert User.objects.filter(email=same_email).count() == len(five_tenants)

    def test_create_users_same_tenant_with_same_email(self, das_tenant):
        same_email = "same@email.com"

        with pytest.raises(ValidationError):
            for _ in range(0, 2):
                User.objects.create(
                    username=faker.profile()["username"],
                    password="password",
                    email=same_email,
                    das_tenant=das_tenant,
                )

    def test_create_user_same_tenant_with_no_email(self, das_tenant):
        usernames = ["username1", "username2", "username3"]

        for username in usernames:
            User.objects.create(
                username=username,
                password="password",
                das_tenant=das_tenant,
            )

        assert User.objects.filter(
            username__in=usernames,
            das_tenant=das_tenant,
            email__isnull=True,
        ).count() == len(usernames)
