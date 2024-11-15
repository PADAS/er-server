import pytest
from django.urls import reverse


@pytest.mark.usefixtures("tenant_settings", "das_tenant")
@pytest.mark.django_db
class TestEventViewListing:
    """Test event view listing methods."""

    base_url = reverse("events")

    def test_events_list(self, superuser_client, five_events) -> None:
        response = superuser_client.get(self.base_url)

        assert response.status_code == 200

    def test_events_list_with_multiple_event_ids(self, superuser_client, five_events) -> None:
        event_1 = five_events[0]
        event_2 = five_events[2]

        url = f"{self.base_url}?event_ids={event_1.pk}&event_ids={event_2.pk}"

        response = superuser_client.get(url)
        results = response.data["results"]

        assert response.status_code == 200
        assert len(results) == 2

        ids_expected = [str(event_1.pk), str(event_2.pk)]

        assert all(event_obj.get("id") in ids_expected for event_obj in results)
