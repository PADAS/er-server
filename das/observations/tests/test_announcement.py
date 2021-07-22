import django.contrib.auth
from core.tests import BaseAPITest
from django.urls import reverse
from observations.models import Announcement
from observations.views import AnnouncementsView
from .testdata.sample_topics import announcement

User = django.contrib.auth.get_user_model()


class AnnouncementTestCase(BaseAPITest):

    def setUp(self):
        super(AnnouncementTestCase, self).setUp()

        self.admin_user = User.objects.create_superuser(username="superuser",
                                                        password="adfsfds32423",
                                                        email="super@user.com")

        for post in announcement['topic_list']['topics']:
            Announcement.objects.create(title=post['title'],
                                        description=post['cooked'],
                                        additional=dict(slug=post["slug"],
                                                        id=post['id'],
                                                        fancy_title=post["fancy_title"],
                                                        created_at=post["created_at"],
                                                        category_id=post["category_id"],
                                                        last_poster_username=post["last_poster_username"]
                                                        ),
                                        link=f"https://community.earthranger.com/t/{post['id']}")

    def test_api_to_get_news(self):
        url = reverse('news-view')
        request = self.factory.get(url)
        self.force_authenticate(request, self.app_user)
        response = AnnouncementsView.as_view()(request)
        assert response.status_code == 200
        assert len(response.data['results']) == 6

        Announcement.objects.create(title='example', link='https://earthranger.com')

    def test_api_to_mark_topic_read(self):
        url = reverse('news-view')
        ids = ''
        for i in list(Announcement.objects.values_list('id', flat=True)):
            ids += f'{i},'

        url += f'?read={ids[:-1]}'
        request = self.factory.post(url)
        self.force_authenticate(request, self.app_user)
        response = AnnouncementsView.as_view()(request)
        assert response.status_code == 200

        url = reverse('news-view')
        request = self.factory.get(url)
        self.force_authenticate(request, self.app_user)
        response = AnnouncementsView.as_view()(request)
        assert response.status_code == 200

        for r in response.data['results']:
            assert r.get('read') is True

        # this user:  self.admin_user has not read the notification
        request = self.factory.get(url)
        self.force_authenticate(request, self.admin_user)
        response = AnnouncementsView.as_view()(request)
        assert response.status_code == 200

        for r in response.data['results']:
            assert r.get('read') is False
