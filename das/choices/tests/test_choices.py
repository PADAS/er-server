import json
import os
from typing import NamedTuple

import django.contrib.auth
import pytest
from django.urls import reverse

from choices.models import Choice

pytestmark = pytest.mark.django_db
User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')


class ChoiceDetails(NamedTuple):
    choices: Choice
    user: User


@pytest.fixture
def choices_fixture(db):
    Choice.objects.all().delete()

    Choice.objects.create(model='activity.eventtype',
                          field='wildlifesighting_species',
                          value='elephant',
                          display='Elephant')

    Choice.objects.create(model='activity.eventtype',
                          field='wildlifesighting_species',
                          value='rhino',
                          display='Rhino')

    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                    is_staff=True, **user_const)

    return ChoiceDetails(choices=Choice.objects.all(), user=user)


def test_get_all_choices(choices_fixture, client):
    choices, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse('choices')
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data['results']) == 2


def test_single_choice(choices_fixture, client):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    client.force_login(user)
    url = reverse('choice', kwargs={'id': choice_id})
    response = client.get(url)
    assert response.status_code == 200
    assert response.data.get('id') == choice_id


def test_add_choice(choices_fixture, client):
    choices, user = choices_fixture.choices, choices_fixture.user

    client.force_login(user)
    url = reverse('choices')
    data = {
        "model": "activity.eventtype",
        "field": "wildlifesighting_species",
        "value": "pelican",
        "display": "Pelican",
        "is_active": True
    }
    response = client.post(url, data=data)
    qcount = Choice.objects.all().count()
    assert response.status_code == 201
    assert qcount == 3


def test_update_choice(choices_fixture, client):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    client.force_login(user)
    url = reverse('choice', kwargs={'id': choice_id})
    data = {"value": "updated value"}
    response = client.patch(url, data=json.dumps(data), content_type='application/json')
    assert response.status_code == 200


def test_softdelete_choice(choices_fixture, client):
    choices, user = choices_fixture.choices, choices_fixture.user
    choice_id = str(choices.first().id)

    disabled_choices = Choice.objects.get_inactive_choices().count()
    assert disabled_choices == 0

    client.force_login(user)
    url = reverse('choice', kwargs={'id': choice_id})
    response = client.delete(url)
    assert response.status_code == 204

    disabled_choices = Choice.objects.get_inactive_choices().count()
    assert disabled_choices == 1


