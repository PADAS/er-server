import django.contrib.auth
from django.urls import reverse

from accounts.views import UserView
from activity.models import EventCategory
from activity.views import EventCategoriesView, EventCategoryView
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()


class EventCategoryTest(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.event_category_url = reverse(
            'admin:activity_eventcategory_changelist')
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

    def test_create_event_category_with_restricted_character(self):
        EventCategory.objects.create(value='.', display='Testing')

        url = 'api/v1.0/user/me'
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = UserView.as_view()(request, id=self.user.id)
        self.assertEqual(response.status_code, 200)

    def test_create_event_categories_perms(self):
        # add new event-category (user with event-category permission)
        url = reverse('event-categories')
        data = {
            "value": "ec_value",
            "display": "ec_display",
            "flag": "user"
        }
        request = self.factory.post(url, data=data)
        self.force_authenticate(request, self.user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data)

        # user with no event-category permission should not be able to add new event-category.
        request = self.factory.post(url, data=data)
        self.force_authenticate(request, self.no_perms_user)
        response = EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_retrieve_event_category(self):
        eventcategory_id = str(EventCategory.objects.first().id)
        url = reverse('event-category',
                      kwargs={'eventcategory_id': eventcategory_id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(
            request, eventcategory_id=eventcategory_id)
        self.assertEqual(response.status_code, 200)

    def test_patch_event_category(self):
        eventcategory_id = str(EventCategory.objects.first().id)
        url = reverse('event-category',
                      kwargs={'eventcategory_id': eventcategory_id})
        data = {'value': "new-value"}
        request = self.factory.patch(url, data)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(
            request, eventcategory_id=eventcategory_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('value'), data.get('value'))

    def test_delete_event_category(self):
        eventcategory_id = str(EventCategory.objects.first().id)
        url = reverse('event-category',
                      kwargs={'eventcategory_id': eventcategory_id})
        request = self.factory.delete(url)
        self.force_authenticate(request, self.user)
        response = EventCategoryView.as_view()(
            request, eventcategory_id=eventcategory_id)
        self.assertEqual(response.status_code, 204)
