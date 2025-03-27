import uuid

import pytest

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from das.tracking.models import SourcePlugin


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
def test_source_plugin_admin_change_list_with_missing_plugin(superuser_client, source):
    """
    Test that SourcePluginAdmin view handles missing plugin relations.
    """

    content_type = ContentType.objects.first()
    # Create a SourcePlugin with no valid plugin relation
    source_plugin = SourcePlugin.objects.create(
        id=uuid.uuid4(),
        source=source,
        plugin_type=content_type,
        plugin_id=uuid.uuid4(),  # non-existent UUID
        status=SourcePlugin.STATUS_ENABLED,
    )

    # SourcePlugin admin changelist URL
    url = reverse("admin:tracking_sourceplugin_changelist")
    response = superuser_client.get(url)

    # Verify the response
    assert response.status_code == 200

    # Verify that the error is shown in the response
    content = response.content.decode("utf-8")
    assert "Plugin not properly configured" in content
    assert str(source_plugin.id) in content
    assert str(content_type.id) in content
    assert str(source_plugin.plugin_id) in content


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch", "tenant_settings")
def test_source_plugin_admin_detail_with_missing_plugin(superuser_client, source):
    """
    Test that the detail view works with missing plugin relations.
    """

    # Get a content type for the generic relation
    content_type = ContentType.objects.first()

    source_plugin = SourcePlugin.objects.create(
        id=uuid.uuid4(),
        source=source,
        plugin_type=content_type,
        plugin_id=uuid.uuid4(),  # Use a non-existent UUID
        status=SourcePlugin.STATUS_ENABLED,
    )

    # SourcePlugin admin detail/change URL
    url = reverse("admin:tracking_sourceplugin_change", args=[source_plugin.id])
    response = superuser_client.get(url)

    # Verify the response
    assert response.status_code == 200

    # Verify the source plugin is in the response
    content = response.content.decode("utf-8")
    assert str(source_plugin.id) in content
