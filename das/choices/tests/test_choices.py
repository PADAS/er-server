import json
import os
import uuid
from typing import Any, List, NamedTuple

import pytest

from django.urls import reverse

from choices.models import Choice
from choices.views import ChoiceView
from utils.tests_tools import is_url_resolved

pytestmark = pytest.mark.django_db
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests")


class ChoiceDetails(NamedTuple):
    choices: Choice
    user: Any
    created_choices: List[Choice]


@pytest.fixture
def choices_fixture(db, das_tenant_monkeypatch, django_user_model):
    """Create four choices in the current tenant with unique values (parallel-safe)."""
    Choice.objects.all().delete()
    suffix = uuid.uuid4().hex[:8]
    choices_data = [
        {
            "model": "activity.eventtype",
            "field": "wildlifesighting_species",
            "value": f"elephant-{suffix}",
            "display": "Elephant",
            "das_tenant": das_tenant_monkeypatch,
        },
        {
            "model": "activity.eventtype",
            "field": "wildlifesighting_species",
            "value": f"rhino-{suffix}",
            "display": "Rhino",
            "das_tenant": das_tenant_monkeypatch,
        },
        {
            "model": "activity.eventtype",
            "field": "wildlifesighting_reporter_type",
            "value": f"ranger-{suffix}",
            "display": "Park Ranger",
            "das_tenant": das_tenant_monkeypatch,
        },
        {
            "model": "activity.eventtype",
            "field": "wildlifesighting_condition_status",
            "value": f"healthy-{suffix}",
            "display": "Healthy",
            "das_tenant": das_tenant_monkeypatch,
        },
    ]

    Choice.objects.bulk_create([Choice(**data) for data in choices_data])
    created_choices = list(
        Choice.objects.filter(das_tenant=das_tenant_monkeypatch, model="activity.eventtype").order_by("field", "value")
    )

    user_const = dict(last_name="last", first_name="first")
    user = django_user_model.objects.create_user(
        "user", "user@test.com", "all_perms_user", is_superuser=True, is_staff=True, **user_const
    )

    return ChoiceDetails(choices=Choice.objects.all(), user=user, created_choices=created_choices)


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_get_all_choices(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse("choices")
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data["results"]) == 9


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_get_all_choices_filtering(client, choices_fixture, five_choices):
    choices, user = choices_fixture.choices, choices_fixture.user

    Choice.objects.filter(id=choices[0].id).update(is_active=False)
    Choice.objects.filter(id=choices[1].id).update(is_active=False)

    client.force_login(user)
    url = reverse("choices")
    response = client.get(
        url,
        {
            "field": "wildlifesighting_species,wildlifesighting_reporter_type",
            "model": "activity.eventtype",
            "include_inactive": True,
        },
    )
    assert response.status_code == 200
    assert len(choices.all()) == 9
    assert len(response.data["results"]) == 3  # assert only filtered items are returned

    response = client.get(url, {"include_inactive": False})
    assert response.status_code == 200
    assert len(response.data["results"]) == 7  # assert only active choices are returned

    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data["results"]) == 7  # assert only active choices when include_inactive is not sent


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_field(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user
    client.force_login(user)

    url = reverse("choices")
    response = client.get(url, {"field": "wildlifesighting_species"})
    assert response.status_code == 200
    assert len(response.data["results"]) == 2  # assert filtered items return choices added by choices_fixture


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_multiple_fields(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user
    client.force_login(user)

    url = reverse("choices")
    response = client.get(url, {"field": "wildlifesighting_species,wildlifesighting_reporter_type"})
    assert response.status_code == 200
    assert len(response.data["results"]) == 3  # assert filtered items return choices added by choices_fixture


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_invalid_field(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user
    client.force_login(user)

    url = reverse("choices")
    response = client.get(url, {"field": "invalid_field"})
    assert response.status_code == 400
    assert "field" in response.data
    assert "is not one of the available choices." in response.content.decode("utf-8")


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_model(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse("choices")
    response = client.get(url, {"model": "activity.eventtype"})
    assert response.status_code == 200
    assert len(response.data["results"]) == 4  # assert filtered items return choices added by choices_fixture


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_invalid_model(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse("choices")
    response = client.get(url, {"model": "invalid_model"})
    assert response.status_code == 400
    assert "model" in response.data
    assert "is not one of the available choices." in response.content.decode("utf-8")


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_filter_by_model_and_field(client, choices_fixture, five_choices):
    _, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse("choices")
    response = client.get(url, {"model": "activity.eventtype", "field": "wildlifesighting_species"})
    assert response.status_code == 200
    assert len(response.data["results"]) == 2  # assert filtered items return choices added by choices_fixture


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_single_choice(client, choices_fixture):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    client.force_login(user)
    url = reverse("choice", kwargs={"id": choice_id})
    response = client.get(url)
    assert response.status_code == 200
    assert response.data.get("id") == choice_id


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_add_choice(client, choices_fixture):
    _, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse("choices")
    data = {
        "model": "activity.eventtype",
        "field": "wildlifesighting_species",
        "value": "pelican",
        "display": "Pelican",
        "is_active": True,
    }
    response = client.post(url, data=data)
    qcount = Choice.objects.all().count()
    assert response.status_code == 201
    assert qcount == 5


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_update_choice(client, choices_fixture):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    client.force_login(user)
    url = reverse("choice", kwargs={"id": choice_id})
    data = {"value": "updated value"}
    response = client.patch(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == 200


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_softdelete_choice(client, choices_fixture):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    disabled_choices = Choice.objects.filter_inactive_choices().count()
    assert disabled_choices == 0

    client.force_login(user)
    url = reverse("choice", kwargs={"id": choice_id})
    response = client.delete(url)
    assert response.status_code == 200

    disabled_choices = Choice.objects.filter_inactive_choices().count()
    assert disabled_choices == 1


@pytest.mark.django_db()
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestChoicesViews:
    def test_url_resolving(self, choice):
        api_path = f"choices/{choice.pk}/"
        assert is_url_resolved(api_path=api_path, view=ChoiceView)

    def test_read_inactive_choice(self, client, choices_fixture):
        choices, user, created_choices = (
            choices_fixture.choices,
            choices_fixture.user,
            choices_fixture.created_choices,
        )
        rhino_choice = next(c for c in created_choices if "rhino" in c.value)
        Choice.objects.filter(id=rhino_choice.id).update(is_active=False)

        assert Choice.objects.filter(id=rhino_choice.id).get().is_active is False

        data = dict(
            model="activity.eventtype",
            field="wildlifesighting_species",
            value=rhino_choice.value,
            display=rhino_choice.display,
        )

        client.force_login(user)
        url = reverse("choices")
        response = client.post(url, data=data)
        assert response.status_code == 409
