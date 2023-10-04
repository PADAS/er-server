import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from factory import Faker

from factories import TenantFactory


@pytest.fixture
def five_tenants():
    previous_tenant = get_current_tenant()

    yield TenantFactory.create_batch(
        size=5,
        id=Faker("uuid4"),
        domain=Faker("domain_name"),
    )
    set_current_tenant(previous_tenant)
