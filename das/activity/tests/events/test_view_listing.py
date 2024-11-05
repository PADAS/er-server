import pytest


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventViewListing:
    """Test event view listing methods."""
