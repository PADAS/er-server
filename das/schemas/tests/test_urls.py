import pytest

from django.urls import reverse

from choices.models import Choice

app_name = "tests"
urlpatterns = []


@pytest.mark.django_db
@pytest.mark.parametrize("view", ["users", "subjects", "choices"])
def test_get_dynamic_schemas(superuser_client, view):
    url = reverse(f"schemas:{view}")
    response = superuser_client.get(url)

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for item in data["oneOf"]:
        assert item["const"]
        assert item["title"]


@pytest.mark.django_db
def test_get_choices_dynamic_schemas(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(url)

    choices = Choice.objects.all()
    choice_ids = [str(choice.id) for choice in choices]
    choice_displays = [choice.display for choice in choices]
    choice_models = [choice.model for choice in choices]

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for item in data["oneOf"]:
        assert item["const"] in choice_ids
        assert item["title"] in choice_displays
        assert item["description"] in choice_models
        assert item["x-field"]
        assert "x-ordernum" in item
        assert "x-icon" in item
        assert "x-value" in item


@pytest.mark.django_db
def test_get_dynamic_schema_choices_filtered(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?fields=firerep_status,carcassrep_ageofcarcass")

    Choice.objects.filter(id=Choice.objects.first().id).update(field="firerep_status")
    Choice.objects.filter(id=Choice.objects.last().id).update(field="carcassrep_ageofcarcass")

    not_in_filter_choices = [
        str(choice.id)
        for choice in Choice.objects.exclude(field__in=["firerep_status", "carcassrep_ageofcarcass"]).all()
    ]
    filtered_choices = [
        str(choice.id)
        for choice in Choice.objects.filter(field__in=["firerep_status", "carcassrep_ageofcarcass"]).all()
    ]

    assert response.status_code == 200
    for item in response.json()["oneOf"]:
        assert item["const"] in filtered_choices
        assert item["const"] not in not_in_filter_choices


@pytest.mark.django_db
def test_choices_value_as_title(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?s_title=value")

    data = response.json()

    assert response.status_code == 200
    for item in data["oneOf"]:
        assert item["title"] == item["x-value"]
