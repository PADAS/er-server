from django.core.management import call_command

from accounts.models import User
from accounts.views import UsersCsvView
from core.tests import BaseAPITest


class UsersCSVExportTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        call_command("loaddata_with_tenant", "accounts_choices.json")
        call_command("loaddata_with_tenant", "initial_admin.yaml")
        call_command("loaddata_with_tenant", "iOS_user.yaml")
        self.superuser = User.objects.get(username="admin")
        self.ios_user = User.objects.get(username="ios")

    def test_csv_metadata(self):
        # Test CSV export API success.
        self.request = self.factory.get(self.api_base + "/users/csv/?additional.tech=iOS")
        self.force_authenticate(self.request, self.superuser)
        response = UsersCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

        # Test CSV file export content
        csv_data = response.content.decode("utf-8").split("\r\n")
        # Remove header and empty line from csv_data to get actual values.
        csv_data = csv_data[1:-1]
        self.assertEqual(len(csv_data), 1)
        self.assertEqual(csv_data[0].split(",")[-1], self.ios_user.email)
