import uuid

import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from faker import Faker

from django.forms import ValidationError

from accounts.models import User

faker = Faker()


@pytest.mark.django_db
class TestUserTenant:
    def test_create_users_diff_tenant_with_same_email(self, five_tenants):
        same_email = "same@email.com"

        previous_tenant = get_current_tenant()

        for tenant in five_tenants:
            set_current_tenant(tenant)
            user = User.objects.create_user(username=faker.profile()["username"], password="password", email=same_email)
            assert uuid.UUID(tenant.id) == user.das_tenant.id
            assert same_email == user.email

        set_current_tenant(previous_tenant)
        assert User.objects.filter(email=same_email).count() == len(five_tenants)

    def test_create_users_same_tenant_with_same_email(self, das_tenant):
        same_email = "same@email.com"

        with pytest.raises(ValidationError):
            for _ in range(0, 2):
                User.objects.create_user(
                    username=faker.profile()["username"],
                    password="password",
                    email=same_email,
                    das_tenant=das_tenant,
                )

    def test_create_user_same_tenant_with_no_email(self, das_tenant):
        usernames = [faker.profile()["username"], faker.profile()["username"], faker.profile()["username"]]
        set_current_tenant(das_tenant)
        for username in usernames:
            User.objects.create_user(username=username, password="password")

        assert User.objects.filter(
            username__in=usernames,
            email__isnull=True,
        ).count() == len(usernames)
