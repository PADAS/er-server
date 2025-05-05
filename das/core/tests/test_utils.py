import pytest

from django.conf import settings
from django.test import TestCase

from core.utils import get_site_name, is_uuid


class TestUtils(TestCase):
    def test_site_name(self):
        site_urls = ["https://mysite.pamdas.org", "https://mysite.apn.pamdas.org"]
        site_name = "mysite"
        for site in site_urls:
            settings.UI_SITE_URL = site
            self.assertEqual(site_name, get_site_name())


@pytest.mark.django_db
class TestIsUUD:
    @pytest.mark.parametrize(
        "string,expected",
        [
            ("f9b2cbd3-a82e-4aec-b46e-4ebf5bdbd441", True),
            ("this-is-not-a-uuid", False),
            (12, False),
        ],
    )
    def test_string_is_uud(self, string, expected):
        is_string_uuid = is_uuid(string)

        assert is_string_uuid is expected
