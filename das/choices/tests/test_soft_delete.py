from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.urls import reverse

from core.tests import BaseAPITest
from choices.models import Choice
from choices.admin import ChoiceAdmin


class MockSuperUser:
    def has_perm(self, perm):
        return True


class TestSoftDelete(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.request_factory = RequestFactory()
        self.admin = ChoiceAdmin(model=Choice, admin_site=self.site)

    def create_choices(self):
        for choice in Choice.objects.all():
            choice.delete()

        choice = Choice.objects.create(
            model='activity.eventtype',
            field='wildlifesighting_species',
            value='elephant',
            display='Elephant',
        )

        choice.save()

        choice = Choice.objects.create(
            model='activity.eventtype',
            field='wildlifesighting_species',
            value='rhino',
            display='Rhino',
        )
        choice.save()

    def test_admin_get_queryset(self):
        """Test get_querysets returns active choices"""

        self.create_choices()
        request = self.request_factory.get('/admin')
        request.user = MockSuperUser()

        querysets = self.admin.get_queryset(request)
        self.assertQuerysetEqual(querysets,
                                 Choice.objects.all(),
                                 transform=lambda x: x)

        choice = Choice.objects.filter(value='rhino')
        choice.disable_choices()

        self.assertNotEqual(self.admin.get_queryset(request),
                            Choice.objects.all())

    def test_admin_soft_delete(self):
        self.create_choices()

        obj = Choice.objects.filter(value='rhino')
        obj.disable_choices()
        self.assertQuerysetEqual(obj,
                                 Choice.objects.filter_inactive_choices(),
                                 transform=lambda x: x)

        is_active = [i.is_active for i in obj]
        self.assertFalse(is_active[0])
