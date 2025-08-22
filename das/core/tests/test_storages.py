import os.path
import unicodedata

import pytest

from core.storages import TenantGoogleCloudStorage


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestTenantStorages:
    @pytest.mark.parametrize(
        "path_sample",
        [
            {"path": "zoo/upload/2024/3/19", "legacy_path": "upload/2024/03/19"},
            {"path": "zoo/upload/2024/3/1", "legacy_path": "upload/2024/03/01"},
            {"path": "zoo/upload/2021/3/19", "legacy_path": "upload/2021/03/19"},
            {"path": "upload/2024/03/19", "legacy_path": "upload/2024/03/19"},
        ],
    )
    def test_with_legacy_month_day_file_paths(self, path_sample):
        tgcs = TenantGoogleCloudStorage()
        assert path_sample["legacy_path"] == tgcs.remove_tenant_from_filename(path_sample["path"])

    def test_retrieve_file_by_tenant_and_nontenant_path(self):
        filename = "path/path/filename.png"
        filename_with_tenant = os.path.join(self.tenant_settings.slug_name, filename)

        tgcs = TenantGoogleCloudStorage()

        assert filename == tgcs.remove_tenant_from_filename(filename_with_tenant)

    def test_generate_nfd_filename_variants_with_ascii_filename(self):
        """Test that ASCII filenames return only the original variant."""
        tgcs = TenantGoogleCloudStorage()
        filename = "simple_file.txt"
        variants = tgcs.generate_nfd_filename_variants(filename)

        assert len(variants) == 1
        assert variants[0] == filename

    def test_generate_nfd_filename_variants_with_unicode_filename(self):
        """Test that Unicode filenames generate NFD variants."""
        tgcs = TenantGoogleCloudStorage()

        # Test with a filename containing combining characters
        # "é" can be represented as "e" + combining acute accent (U+0301)
        filename = "café.txt"
        variants = tgcs.generate_nfd_filename_variants(filename)

        # Should have at least 2 variants: original and NFD
        assert len(variants) >= 2

        # Original should be in the list
        assert filename in variants

        # NFD variant should be different and also in the list
        nfd_variant = unicodedata.normalize("NFD", filename)
        assert nfd_variant in variants
        assert nfd_variant != filename

    def test_generate_nfd_filename_variants_with_nfd_filename(self):
        """Test that already NFD filenames generate NFC variants."""
        tgcs = TenantGoogleCloudStorage()

        # Create an NFD filename manually
        nfd_filename = "cafe" + "\u0301" + ".txt"  # "cafe" + combining acute accent
        variants = tgcs.generate_nfd_filename_variants(nfd_filename)

        # Should have at least 2 variants: original NFD and NFC
        assert len(variants) >= 2

        # Original NFD should be in the list
        assert nfd_filename in variants

        # NFC variant should be different and also in the list
        nfc_variant = unicodedata.normalize("NFC", nfd_filename)
        assert nfc_variant in variants
        assert nfc_variant != nfd_filename

    def test_generate_search_paths_includes_unicode_variants(self):
        """Test that search paths include Unicode variants."""
        tgcs = TenantGoogleCloudStorage()
        filename = "café.txt"

        search_paths = tgcs.generate_search_paths(filename)

        # Should have more paths than just the basic tenant variants
        # due to Unicode normalization
        assert len(search_paths) > 3

        # Should include the original filename
        assert filename in search_paths

        # Should include NFD variant
        nfd_variant = unicodedata.normalize("NFD", filename)
        assert nfd_variant in search_paths

        # Should include tenant-prefixed versions
        tenant_filename = f"{self.tenant_settings.slug_name}/{filename}"
        assert tenant_filename in search_paths

        # Should include tenant-prefixed NFD version
        tenant_nfd_filename = f"{self.tenant_settings.slug_name}/{nfd_variant}"
        assert tenant_nfd_filename in search_paths

    def test_generate_search_paths_removes_duplicates(self):
        """Test that search paths don't contain duplicates."""
        tgcs = TenantGoogleCloudStorage()
        filename = "café.txt"

        search_paths = tgcs.generate_search_paths(filename)

        # Check for duplicates
        assert len(search_paths) == len(set(search_paths))

        # All paths should be unique
        seen = set()
        for path in search_paths:
            assert path not in seen
            seen.add(path)

    def test_generate_search_paths_with_complex_unicode(self):
        """Test with more complex Unicode characters."""
        tgcs = TenantGoogleCloudStorage()

        # Test with multiple combining characters
        filename = "naïve_café_voilà.txt"
        search_paths = tgcs.generate_search_paths(filename)

        # Should generate multiple variants
        assert len(search_paths) > 3

        # Should include NFD variant
        nfd_variant = unicodedata.normalize("NFD", filename)
        assert nfd_variant in search_paths

        # Should include tenant variants
        tenant_filename = f"{self.tenant_settings.slug_name}/{filename}"
        assert tenant_filename in search_paths

        tenant_nfd_filename = f"{self.tenant_settings.slug_name}/{nfd_variant}"
        assert tenant_nfd_filename in search_paths

    def test_generate_search_paths_preserves_order(self):
        """Test that search paths preserve the order of generation."""
        tgcs = TenantGoogleCloudStorage()
        filename = "test.txt"

        search_paths = tgcs.generate_search_paths(filename)

        # First path should be the original filename
        assert search_paths[0] == filename

        # Should include tenant-removed version (which for a filename without tenant prefix is the same)
        expected_second = tgcs.remove_tenant_from_filename(filename)
        assert expected_second in search_paths

        # Should include tenant-added version
        expected_third = tgcs.add_tenant_to_filename(filename)
        assert expected_third in search_paths

        # Should include Unicode variants
        unicode_variants = tgcs.generate_nfd_filename_variants(filename)
        for variant in unicode_variants:
            if variant != filename:  # Skip the original
                assert variant in search_paths
