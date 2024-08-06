import datetime
import re
from pathlib import Path

import google.auth
import google.auth.transport
from google.auth import impersonated_credentials
from google.auth.transport import requests
from google.cloud.exceptions import NotFound
from storages.backends.gcloud import GoogleCloudStorage

from utils.tenant.thread import get_tenant_settings


class TenantGoogleCloudStorage(GoogleCloudStorage):
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

    def _open(self, name, mode="rb"):
        # Define a list of paths to try.
        paths_to_try = [name, self.remove_tenant_from_filename(name)]

        for path in paths_to_try:
            try:
                return super()._open(path, mode=mode)
            except FileNotFoundError:
                continue

        # If none of the paths lead to a file, raise a FileNotFoundError.
        raise FileNotFoundError(f"File not found at any of the paths: {paths_to_try}")

    def _get_blob(self, name):
        paths_to_try = [name, self.remove_tenant_from_filename(name)]

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
