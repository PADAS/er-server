import pytest

from factories import TenantFactory
from django_multitenant.utils import set_current_tenant, get_current_tenant

@pytest.fixture
def five_tenants():
    previous_tenant = get_current_tenant()
    yield TenantFactory.create_batch(5)
    set_current_tenant(previous_tenant)
