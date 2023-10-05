import uuid

import pytest

from django.test import TestCase

from choices.models import Choice
from observations.forms import SubjectForm
from observations.models import SEX_MALE, Subject, SubjectSubType, SubjectType


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SubjectAdditionalTest(TestCase):
    def setUp(self):
        wildlife_subject_type, created = SubjectType.objects.get_or_create(
            value="wildlife", defaults=dict(display="wildlife")
        )
        subject_subtype, created = SubjectSubType.objects.get_or_create(
            value="cheetah", defaults=dict(display="cheetah", subject_type=wildlife_subject_type)
        )
        region, created = Choice.objects.get_or_create(
            model="observations.region", field="region", value="Lewa", display="Lewa"
        )
        country, created = Choice.objects.get_or_create(
            model="observations.region", field="country", value="DRC", display="DRC"
        )

    def test_subject_creation(self):
        additional_data = {
            "rgb": "203, 223, 54",
            "sex": SEX_MALE,
            "region": "Lewa",
            "country": "DRC",
            "tm_animal_id": "some-external-ID",
            "external_id": "some other id",
            "external_name": "some external name",
        }
        form_data = {"id": uuid.uuid4(), "name": "Henry", "subject_subtype": "cheetah", "is_active": "on"}
        form_data = {**form_data, **additional_data}
        form = SubjectForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()

        subject, created = Subject.objects.get_or_create(name="Henry")
        self.assertTrue(all(item in subject.additional.items() for item in additional_data.items()))
