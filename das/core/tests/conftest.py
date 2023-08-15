import pytest

from factories import TenantFactory


@pytest.fixture
def five_tenants():
    return TenantFactory.create_batch(5)
