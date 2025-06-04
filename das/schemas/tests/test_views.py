import pytest

from django.urls import reverse

from choices.models import Choice
from factories import SubjectFactory
from observations.models import SubjectGroup


@pytest.mark.django_db
@pytest.mark.parametrize("view", ["users", "subjects", "choices", "spatial_features", "event_types"])
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
    choice_values = [choice.value for choice in choices]
    choice_displays = [choice.display for choice in choices]

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for item in data["oneOf"]:
        assert item["const"] in choice_ids
        assert item["title"] in choice_values
        assert item["description"] in choice_displays


@pytest.mark.django_db
def test_get_dynamic_schema_choices_filtered(superuser_client):
    Choice.objects.filter(id=Choice.objects.first().id).update(field="firerep_status")
    Choice.objects.filter(id=Choice.objects.last().id).update(field="carcassrep_ageofcarcass")

    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?field=firerep_status,carcassrep_ageofcarcass")

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
def test_choices_display_as_title(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?s_title=display")

    data = response.json()

    assert response.status_code == 200
    for item in data["oneOf"]:
        assert item["description"] == item["title"]


@pytest.mark.django_db
def test_dynamic_subjects_filtered_by_subtypes(superuser_client):
    two_subjects = SubjectFactory.create_batch(2)
    last_subject = SubjectFactory.create()

    sgrp1 = SubjectGroup.objects.create(name="Subject Group 1")
    sgrp2 = SubjectGroup.objects.create(name="Subject Group 2")
    sgrp1.subjects.add(two_subjects[0])
    sgrp2.subjects.add(last_subject)

    sgrp1.save()
    sgrp2.save()

    url = reverse("schemas:subjects")
    response = superuser_client.get(f"{url}?subject_subtypes={last_subject.subject_subtype.value}")

    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json["oneOf"])
    for item in response_json["oneOf"]:
        # assert attached first subject filtered by first group
        assert item["const"] == str(last_subject.id)
        assert item["title"] == str(last_subject.name)
        # assert other created subjects aren't present
        assert item["const"] not in [str(two_subjects[0].id), str(two_subjects[1].id)]
        assert item["title"] not in [str(two_subjects[0].name), str(two_subjects[1].name)]


@pytest.mark.django_db
def test_dynamic_subjects_filtered_by_group_id(superuser_client):
    two_subjects = SubjectFactory.create_batch(2)
    last_subject = SubjectFactory.create()

    sgrp1 = SubjectGroup.objects.create(name="Subject Group 1")
    sgrp2 = SubjectGroup.objects.create(name="Subject Group 2")
    sgrp1.subjects.add(two_subjects[0])
    sgrp2.subjects.add(last_subject)

    sgrp1.save()
    sgrp2.save()

    url = reverse("schemas:subjects")
    response = superuser_client.get(f"{url}?subject_group={sgrp1.id}")
    assert response.status_code == 200

    response_json = response.json()
    assert len(response_json["oneOf"]) == 1
    for item in response_json["oneOf"]:
        # assert attached first subject filtered by first group
        assert item["const"] == str(two_subjects[0].id)
        assert item["title"] == two_subjects[0].name
        # assert other created subjects aren't present
        assert item["const"] not in [str(two_subjects[1].id), str(last_subject.id)]
        assert item["title"] not in [str(two_subjects[1].name), str(last_subject.name)]
