import os.path

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
