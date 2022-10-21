from django.test import TestCase

from django.conf import settings

import core.utils


class TestUtils(TestCase):
    def test_site_name(self):
        site_urls = ["https://mysite.pamdas.org",
                     "https://mysite.apn.pamdas.org"]
        site_name = "mysite"
        for site in site_urls:
            settings.UI_SITE_URL = site
            self.assertEqual(site_name, core.utils.get_site_name())
