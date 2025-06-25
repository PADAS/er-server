import pytest

from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework.test import APIClient

# Mapping of dynamic schema views to their source views
DYNAMIC_SCHEMA_MAPPINGS = [
    {
        "name": "subjects",
        "url_name": "schemas:subjects",
        "source_url_name": "subjects-list-view",
    },
    {
        "name": "choices",
        "url_name": "schemas:choices",
        "source_url_name": "choices",
    },
    {
        "name": "spatial_features",
        "url_name": "schemas:spatial_features",
        "source_url_name": "mapping:spatialfeature-list",
    },
    {
        "name": "event_types",
        "url_name": "schemas:event_types",
        "source_url_name": "v2-eventtype-list",
    },
    {
        "name": "users",
        "url_name": "schemas:users",
        "source_url_name": "accounts:users",
    },
]


@pytest.mark.django_db
class TestDynamicSchemaErrorConsistency:
    """Test that dynamic schema endpoints return errors consistently with their source endpoints."""

    @pytest.mark.parametrize("mapping", DYNAMIC_SCHEMA_MAPPINGS)
    def test_authentication_errors_consistent(self, mapping):
        """Test that authentication errors are consistent between dynamic schema and source endpoints."""
        client = APIClient()
        client.force_authenticate(user=AnonymousUser())

        dynamic_response = client.get(reverse(mapping["url_name"]))
        source_response = client.get(reverse(mapping["source_url_name"]))

        assert dynamic_response.status_code in [401, 403]
        assert source_response.status_code in [401, 403], (
            f"{mapping['name']}: Dynamic schema returned {dynamic_response.status_code} "
            f"but source returned {source_response.status_code}"
        )

    @pytest.mark.parametrize("mapping", DYNAMIC_SCHEMA_MAPPINGS[:2])  # Only subjects and choices are failing with 403
    def test_permission_errors_consistent(self, mapping, user_client):
        """Test that permission errors are consistent between endpoints."""
        dynamic_response = user_client.get(reverse(mapping["url_name"]))
        source_response = user_client.get(reverse(mapping["source_url_name"]))

        # If one returns 403, both should return 403
        if dynamic_response.status_code == 403:
            assert source_response.status_code == 403, (
                f"{mapping['name']}: Dynamic schema returned 403 " f"but source returned {source_response.status_code}"
            )
        elif source_response.status_code == 403:
            assert dynamic_response.status_code == 403, (
                f"{mapping['name']}: Source returned 403 " f"but dynamic schema returned {dynamic_response.status_code}"
            )
