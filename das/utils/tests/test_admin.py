import csv
from io import StringIO

import pytest

from django.contrib import admin
from django.test import RequestFactory

from choices.models import Choice
from utils.admin import ExportDataActionMixin


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_export_data_as_csv_for_choice(superuser, choice):
    class MockAdmin(ExportDataActionMixin, admin.ModelAdmin):
        fields_to_export = ["model", "field", "value", "display", "icon", "ordernum"]

    mock_admin = MockAdmin(model=Choice, admin_site=admin.site)

    factory = RequestFactory()
    request = factory.post("/admin/choice/")
    request.user = superuser
    queryset = Choice.objects.filter(id=choice.id)
    response = mock_admin.export_data_as_csv(request, queryset)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment; filename=" in response["Content-Disposition"]

    csv_file = StringIO(response.content.decode("utf-8"))
    csv_reader = csv.DictReader(csv_file)

    assert csv_reader.fieldnames == ["model", "field", "value", "display", "icon", "ordernum"]

    rows = list(csv_reader)

    assert rows[0] == {
        "model": choice.model,
        "field": choice.field,
        "value": choice.value,
        "display": choice.display,
        "icon": choice.icon or "",
        "ordernum": str(choice.ordernum),
    }
