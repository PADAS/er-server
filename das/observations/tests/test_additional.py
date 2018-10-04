import uuid

from observations.models import Subject, SubjectType, SubjectSubType
from observations.forms import SubjectFormWithAttributes
from core.tests import BaseAPITest


class SubjectAdditionalTest(BaseAPITest):

    def setUp(self):
        wildlife_subject_type, created = SubjectType.objects.get_or_create(
            value='wildlife', display='wildlife'
        )
        self.subject_subtype, created = SubjectSubType.objects.get_or_create(
            value='cheetah', display='cheetah',
            subject_type=wildlife_subject_type
        )

    def test_subject_creation(self):
        additional_data = {
            'rgb': '203, 223, 54', 'sex': 'male',
            'region': 'Lewa', 'country': 'DRC',
            'birthdate': '27/07/2018', 'other_id': 'Cat526'
        }
        form_data = {
            'id': uuid.uuid4(),
            'name': 'Henry', 'subject_subtype': 'cheetah', 'is_active': 'on'
        }
        form_data = {**form_data, **additional_data}
        form = SubjectFormWithAttributes(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()
        subject, created = Subject.objects.get_or_create(name='Henry')
        self.assertTrue(all(item in subject.additional.items()
                            for item in additional_data.items()))
