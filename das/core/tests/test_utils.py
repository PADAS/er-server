import hashlib
from unittest.mock import patch

import pytest

from django.conf import settings
from django.test import TestCase

from core.utils import DirectoryIconFinder, get_site_name, is_uuid


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


@pytest.mark.django_db
class TestDirectoryIconFinder:
    @pytest.fixture(autouse=True)
    def cleanup(self):  # Execute before and after each test to ensure a clean Singleton state
        original = DirectoryIconFinder._instance
        DirectoryIconFinder._instance = None
        DirectoryIconFinder._cache.clear()

        yield  # Test runs

        DirectoryIconFinder._instance = original

    @patch("core.utils.staticfiles_storage")
    def test_file_metadata_caching(self, mock_storage):
        mock_storage.listdir.return_value = ([], ["test.svg", "ignore.txt"])
        mock_storage.get_modified_time.return_value = 1234567890

        finder = DirectoryIconFinder()

        result1 = finder._file_metadata
        result2 = finder._file_metadata

        assert result1 == result2 == (("test.svg", 1234567890),)
        mock_storage.listdir.assert_called_once_with("sprite-src")

    @patch("core.utils.staticfiles_storage")
    def test_etag_generation(self, mock_storage):
        mock_storage.listdir.return_value = ([], ["icon1.svg", "icon2.png"])
        mock_storage.get_modified_time.return_value = 1234567890

        expected_data = (("icon1.svg", 1234567890), ("icon2.png", 1234567890))
        expected_hash = hashlib.md5(str(expected_data).encode()).hexdigest()

        etag = DirectoryIconFinder.get_etag()
        assert etag == expected_hash

    @patch("core.utils.staticfiles_storage")
    def test_etag_caching(self, mock_storage):
        mock_storage.listdir.return_value = ([], ["test.svg"])
        mock_storage.get_modified_time.return_value = 1234567890

        etag1 = DirectoryIconFinder.get_etag()  # create cache
        etag2 = DirectoryIconFinder.get_etag()  # use cached result

        assert etag1 == etag2
        assert mock_storage.listdir.call_count == 1

    @patch("core.utils.staticfiles_storage", return_value=([], []))
    def test_empty_directory(self, mock_storage):
        finder = DirectoryIconFinder()
        assert finder._file_metadata == tuple()

    @patch("core.utils.staticfiles_storage.listdir", side_effect=Exception("Not found"))
    def test_invalid_directory(self, mock_storage):
        with pytest.raises(Exception) as excinfo:
            finder = DirectoryIconFinder()
            finder._file_metadata

        assert str(excinfo.value) == "Not found"
