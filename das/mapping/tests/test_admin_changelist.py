import pytest

from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureTypeAdminChangelist:
    def test_changelist_loads(self, superuser_client):
        url = reverse("admin:mapping_spatialfeaturetype_changelist")
        response = superuser_client.get(url)
        assert response.status_code == 200

    def test_changeform_add_loads(self, superuser_client):
        url = reverse("admin:mapping_spatialfeaturetype_add")
        response = superuser_client.get(url)
        assert response.status_code == 200
