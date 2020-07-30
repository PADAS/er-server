import django.contrib.auth
from django.urls import reverse

from activity.models import EventCategory
from activity.views import EventCategoriesView
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()


class EventCategoryTest(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.event_category_url = reverse('admin:activity_eventcategory_changelist')
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)
        self.no_perms_user = User.objects.create_user('no_perms_user',
                                                      'das_no_perms@vulcan.com',
                                                      'noperms',
                                                      **user_const)
        EventCategory.objects.create(value='security', display='Security')
        EventCategory.objects.create(value='logistic', display='Logistic')

    def test_no_event_categories_display(self):
        # User with no-perms can't view event categories.
        request = self.factory.get(self.event_category_url)
        self.force_authenticate(request, self.no_perms_user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_view_event_categories_with_perms(self):
        request = self.factory.get(self.event_category_url)
        self.force_authenticate(request, self.user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)
