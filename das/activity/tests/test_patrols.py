from django.core.management import call_command
from core.tests import BaseAPITest
from activity.models import PatrolType


class TestPatrolType(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'test_patroltype')

    def test_patroltype_api(self):
        querysets = PatrolType.objects.all()
        import pdb; pdb.set_trace()