import datetime
import logging
import mimetypes
import re
import unicodedata
from pathlib import Path
from typing import List

import google.auth
import google.auth.transport
from google.auth import impersonated_credentials
from google.auth.transport import requests
from google.cloud.exceptions import NotFound
from storages.backends.gcloud import GoogleCloudStorage

from django.conf import settings

from utils.tenant.thread import get_tenant_settings

logger = logging.getLogger(__name__)


class TenantGoogleCloudStorage(GoogleCloudStorage):
    def generate_nfd_filename_variants(self, filename: str) -> List[str]:
        """Generate NFD (Normalization Form Decomposed) variants of a filename.

        This method creates alternative filename representations that can be used
        to search for files stored with NFD encoding when the database filename
        is in NFC (Normalization Form Canonical Composition) format.

        Args:
            filename (str): The original filename (typically in NFC format)

        Returns:
            list[str]: List of filename variants including NFD versions
        """
        variants = [filename]

        # Generate NFD variant
        nfd_filename = unicodedata.normalize("NFD", filename)
        if nfd_filename != filename:
            variants.append(nfd_filename)

        # Generate NFC variant (in case original was not normalized)
        nfc_filename = unicodedata.normalize("NFC", filename)
        if nfc_filename != filename and nfc_filename not in variants:
            variants.append(nfc_filename)

        return variants

    def generate_search_paths(self, filename: str) -> List[str]:
        """Generate all possible search paths for a filename including Unicode variants.

        This method combines tenant path handling with Unicode normalization
        to create a comprehensive list of paths to search for files.

        Args:
            filename (str): The filename to search for

        Returns:
            list[str]: List of all possible file paths to search
        """
        # Get base paths from existing tenant logic
        base_paths = [filename, self.add_tenant_to_filename(filename), self.remove_tenant_from_filename(filename)]

        # Generate Unicode variants for each base path
        all_paths = []
        for base_path in base_paths:
            unicode_variants = self.generate_nfd_filename_variants(base_path)
            all_paths.extend(unicode_variants)

        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for path in all_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        return unique_paths

    def update_date_in_path_with_fixed_digit_format(self, filename: str) -> str:
        """When MT was implemented, we changed
        the folder name format for the month and day. Previously we used a two character format, preceding single digits with
        "0" zero. The new format does not prefix, even for single digits. (2024/01/01 vs 2024/1/1)

        Here we want to return the legacy path, which requires fixing the date format in some cases

        Args:
            filename (str): the full path and filename of the file stored in GCS

        Returns:
            str: either the original, or the changed filename
        """
        date_pattern = r"(\d{4})/(\d{1,2})/(\d{1,2})"

        def format_date(match):
            year, month, day = match.groups()
            date_obj = datetime.date(year=int(year), month=int(month), day=int(day))
            return date_obj.strftime("%Y/%m/%d")

        return re.sub(date_pattern, format_date, filename)

    def remove_tenant_from_filename(self, filename: str) -> str:
        """In the MT world, we use one GCS bucket for storing all tenant uploads.
        To do that we prefix the path with the tenant slug_name. Legacy files stored pre-multi-tenant
        are still stored withouth the slug_name in the path.

        Args:
            filename (str): the full path and filename of the file stored in GCS

        Returns:
            str: either the original, or the changed filename
        """
        filename_path = Path(filename)
        tenant = get_tenant_settings()
        tenant_path = Path(tenant.slug_name)

        if filename_path.parts and filename_path.parts[0] == str(tenant_path):
            legacy_filename = str(filename_path.relative_to(tenant_path))
            legacy_filename = self.update_date_in_path_with_fixed_digit_format(legacy_filename)
            return legacy_filename
        return filename

    def add_tenant_to_filename(self, filename: str) -> str:
        """Add tenant prefix to filename if it doesn't already have it.

        Args:
            filename (str): the full path and filename of the file stored in GCS

        Returns:
            str: filename with tenant prefix added if not already present
        """
        filename_path = Path(filename)
        tenant = get_tenant_settings()
        tenant_path = Path(tenant.slug_name)
        # If the filename already starts with the tenant slug, return as-is
        if filename_path.parts and filename_path.parts[0] == str(tenant_path):
            return filename
        # Otherwise, add tenant prefix
        return str(tenant_path / filename_path)

    def _force_download_mimetypes(self) -> set[str]:
        return set(getattr(settings, "USERCONTENT_SETTINGS", {}).get("force_download_mimetypes", ()))

    def _save(self, name, content):
        """Stamp safe Content-Type and Content-Disposition on uploads whose mime type is in
        USERCONTENT_SETTINGS["force_download_mimetypes"] (e.g. image/svg+xml, text/html,
        text/javascript). This prevents browsers from rendering active content inline when
        the object is fetched directly from GCS via a signed URL.
        """
        mt, _ = mimetypes.guess_type(name)
        if mt and mt in self._force_download_mimetypes():
            content.content_type = "application/octet-stream"
            saved_name = super()._save(name, content)
            try:
                blob = self.bucket.blob(self._encode_name(self._normalize_name(saved_name)))
                blob.content_disposition = "attachment"
                blob.patch()
            except Exception:
                logger.exception("Failed to set Content-Disposition=attachment on force-download blob %s", saved_name)
            return saved_name
        return super()._save(name, content)

    def _open(self, name, mode="rb"):
        # Use the new Unicode-aware search paths
        paths_to_try = self.generate_search_paths(name)

        for path in paths_to_try:
            try:
                return super()._open(path, mode=mode)
            except FileNotFoundError:
                continue

        # If none of the paths lead to a file, raise a FileNotFoundError.
        raise FileNotFoundError(f"File not found at any of the paths: {paths_to_try}")

    def _get_blob(self, name):
        # Use the new Unicode-aware search paths
        paths_to_try = self.generate_search_paths(name)

        for path in paths_to_try:
            try:
                return super()._get_blob(path)
            except NotFound:
                continue
        raise NotFound(f"File not found at any of the paths: {paths_to_try}")

    def url(self, name, parameters=None):
        """We override url, to support this code running under Google Federated Cloud Identity in
        kubernetes. In that case, we have to sign the url using some meta data from the running instance
        over finding the json auth credentials in a secrets volume

        Args:
            name (_type_): _description_
            parameters (_type_, optional): _description_. Defaults to None.
        """
        credentials = self.get_impersonated_credentials()
        if not parameters:
            parameters = {}
        parameters["credentials"] = credentials

        paths_to_try = self.generate_search_paths(name)

        for path in paths_to_try:
            try:
                if super().exists(path):
                    return super().url(path, parameters)
            except Exception:
                continue
        return super().url(name, parameters)

    def get_impersonated_credentials(self):
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials, project = google.auth.default(scopes=scopes)
        if credentials.token is None:
            credentials.refresh(requests.Request())
        signing_credentials = impersonated_credentials.Credentials(
            source_credentials=credentials,
            target_principal=credentials.service_account_email,
            target_scopes=scopes,
            lifetime=datetime.timedelta(seconds=3600),
            delegates=[credentials.service_account_email],
        )
        return signing_credentials

    def exists(self, name):
        """Check if a file exists using Unicode-aware search paths.

        This method overrides the default exists method to support
        searching for files with different Unicode normalization forms.

        Args:
            name (str): The filename to check

        Returns:
            bool: True if the file exists, False otherwise
        """
        paths_to_try = self.generate_search_paths(name)

        for path in paths_to_try:
            try:
                if super().exists(path):
                    return True
            except Exception:
                continue

        return False

    def size(self, name):
        """Get the size of a file using Unicode-aware search paths.

        This method overrides the default size method to support
        searching for files with different Unicode normalization forms.

        Args:
            name (str): The filename to get size for

        Returns:
            int: The size of the file in bytes
        """
        paths_to_try = self.generate_search_paths(name)

        for path in paths_to_try:
            try:
                return super().size(path)
            except Exception:
                continue

        raise FileNotFoundError(f"File not found at any of the paths: {paths_to_try}")
