import pytest

from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAsyncDelete:
    def test_delete_source_async(self, superuser_client, source, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True

        delete_url = reverse("source-view", kwargs={"id": source.id})
        delete_url += "?async=true"

        response = superuser_client.delete(delete_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert "task_id" in response.data
        assert "location" in response.data

        status_url = response.data["location"]
        status_response = superuser_client.get(status_url)
        assert status_response.status_code == status.HTTP_200_OK
        assert "status" in status_response.data

        assert status_response.data["status"] in ("SUCCESS", "PENDING")
