import csv
import io
import logging
from typing import Any, NamedTuple

import pytest

from django.contrib.admin.sites import AdminSite

from choices.admin import ChoiceAdmin
from choices.models import Choice

pytestmark = pytest.mark.django_db
logger = logging.getLogger(__name__)


class AdminDetails(NamedTuple):
    admin: ChoiceAdmin
    user: Any


@pytest.fixture
def choice_admin_fixture(django_user_model):
    """Setup ChoiceAdmin and superuser for testing"""
    user_const = dict(last_name="admin", first_name="test")
    user = django_user_model.objects.create_user(
        "admin", "admin@test.com", "password", is_superuser=True, is_staff=True, **user_const
    )

    admin_site = AdminSite()
    choice_admin = ChoiceAdmin(Choice, admin_site)

    return AdminDetails(admin=choice_admin, user=user)


@pytest.fixture
def valid_csv_content():
    """Returns valid CSV content for import"""
    return """model,field,value,display,icon,ordernum,is_active
activity.event,priority,high,High Priority,,1,true
activity.event,priority,medium,Medium Priority,,2,true
activity.event,priority,low,Low Priority,,3,true"""


@pytest.fixture
def csv_with_update():
    """Returns CSV content that updates existing choices"""
    return """model,field,value,display,icon,ordernum,is_active
activity.eventtype,wildlifesighting_species,elephant,African Elephant,,1,true
activity.eventtype,wildlifesighting_species,rhino,White Rhino,,2,false"""


@pytest.fixture
def invalid_csv_missing_required():
    """Returns CSV with missing required fields"""
    return """model,field,value,display
activity.event,,high,High Priority
activity.event,priority,,Medium Priority"""


@pytest.fixture
def invalid_csv_wrong_model():
    """Returns CSV with invalid model choice"""
    return """model,field,value,display,icon,ordernum
invalid.model,priority,high,High Priority,,1"""


@pytest.fixture
def csv_with_mixed_errors():
    """Returns CSV with some valid and some invalid rows"""
    return """model,field,value,display,icon,ordernum
activity.event,status,open,Open,,1
invalid.model,status,closed,Closed,,2
activity.event,,pending,Pending,,3
activity.event,status,resolved,Resolved,,4"""


@pytest.fixture
def csv_with_duplicate_in_file():
    """Returns CSV with duplicate entries within the file"""
    return """model,field,value,display,icon,ordernum
activity.event,priority,high,High Priority,,1
activity.event,priority,high,High Priority Duplicate,,2"""


@pytest.mark.usefixtures("tenant_settings")
class TestCSVImportValidation:
    """Test CSV validation logic"""

    def test_validate_csv_all_valid(self, choice_admin_fixture, valid_csv_content):
        """Test validation passes with all valid rows"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(valid_csv_content)

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is True
        assert len(errors) == 0
        assert len(validated_data) == 3
        assert validated_data[0]["data"]["value"] == "high"

    def test_validate_csv_missing_required_fields(self, choice_admin_fixture, invalid_csv_missing_required):
        """Test validation fails with missing required fields"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(invalid_csv_missing_required)

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is False
        assert len(errors) > 0
        # Check that both rows with missing data are reported
        # Row numbers are 1-indexed for data rows (first data row = 1)
        row_numbers = [err["row"] for err in errors]
        assert 1 in row_numbers  # Row with missing field
        assert 2 in row_numbers  # Row with missing value

    def test_validate_csv_invalid_model(self, choice_admin_fixture, invalid_csv_wrong_model):
        """Test validation fails with invalid model choice"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(invalid_csv_wrong_model)

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is False
        assert len(errors) == 1
        # Row numbers are 1-indexed for data rows (first data row = 1)
        assert errors[0]["row"] == 1
        assert "model" in errors[0]["error"].lower()

    def test_validate_csv_mixed_valid_invalid(self, choice_admin_fixture, csv_with_mixed_errors):
        """Test validation identifies only invalid rows"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(csv_with_mixed_errors)

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is False
        assert len(errors) == 2  # Two invalid rows
        # Row numbers are 1-indexed for data rows (first data row = 1)
        row_numbers = [err["row"] for err in errors]
        assert 2 in row_numbers  # Row with invalid model
        assert 3 in row_numbers  # Row with missing field

    def test_validate_csv_empty_file(self, choice_admin_fixture):
        """Test validation fails with empty CSV"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO("")

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is False
        assert len(errors) > 0
        assert "empty" in errors[0]["error"].lower() or "header" in errors[0]["error"].lower()

    def test_validate_csv_missing_headers(self, choice_admin_fixture):
        """Test validation fails with missing required headers"""
        admin = choice_admin_fixture.admin
        csv_content = """value,display
high,High Priority"""
        csv_file = io.StringIO(csv_content)

        is_valid, errors, validated_data = admin.validate_csv_data(csv_file)

        assert is_valid is False
        assert len(errors) > 0
        assert "model" in errors[0]["error"].lower() or "field" in errors[0]["error"].lower()


@pytest.fixture
def csv_with_is_active():
    """Returns CSV content with is_active values"""
    return """model,field,value,display,icon,ordernum,is_active
activity.event,status,active,Active Status,,1,true
activity.event,status,inactive,Inactive Status,,2,false
activity.event,status,pending,Pending Status,,3,1
activity.event,status,archived,Archived Status,,4,0"""


@pytest.fixture
def csv_with_invalid_is_active():
    """Returns CSV content with invalid is_active values"""
    return """model,field,value,display,icon,ordernum,is_active
activity.event,status,active,Active Status,,1,maybe"""


@pytest.mark.usefixtures("tenant_settings")
class TestCSVImport:
    """Test CSV import functionality"""

    def test_import_new_choices(self, choice_admin_fixture, valid_csv_content):
        """Test importing new choices from CSV"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(valid_csv_content)

        initial_count = Choice.objects.count()
        success, message = admin.import_csv_data(csv_file)

        assert success is True
        assert Choice.objects.count() == initial_count + 3

        # Verify imported data
        high_priority = Choice.objects.get(model="activity.event", field="priority", value="high")
        assert high_priority.display == "High Priority"
        assert high_priority.ordernum == 1

    def test_import_updates_existing_choices(self, choice_admin_fixture, csv_with_update):
        """Test that import updates existing choices"""
        admin = choice_admin_fixture.admin

        # Create initial choices for testing updates
        Choice.objects.create(
            model="activity.eventtype", field="wildlifesighting_species", value="elephant", display="Elephant"
        )
        Choice.objects.create(
            model="activity.eventtype", field="wildlifesighting_species", value="rhino", display="Rhino"
        )

        # Get initial elephant choice
        elephant = Choice.objects.get(model="activity.eventtype", field="wildlifesighting_species", value="elephant")
        initial_display = elephant.display

        csv_file = io.StringIO(csv_with_update)
        success, message = admin.import_csv_data(csv_file)

        assert success is True

        # Verify the display was updated
        elephant.refresh_from_db()
        assert elephant.display == "African Elephant"
        assert elephant.display != initial_display

    def test_import_fails_with_validation_errors(self, choice_admin_fixture, invalid_csv_missing_required):
        """Test that import fails when validation errors exist"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(invalid_csv_missing_required)

        initial_count = Choice.objects.count()
        success, message = admin.import_csv_data(csv_file)

        assert success is False
        assert Choice.objects.count() == initial_count  # No changes made

    def test_import_rollback_on_error(self, choice_admin_fixture, csv_with_mixed_errors):
        """Test that import rolls back all changes if any error occurs"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(csv_with_mixed_errors)

        initial_count = Choice.objects.count()
        success, message = admin.import_csv_data(csv_file)

        assert success is False
        assert Choice.objects.count() == initial_count  # No partial imports

        # Verify none of the valid rows were imported
        assert not Choice.objects.filter(model="activity.event", field="status", value="open").exists()

    def test_import_with_is_active_values(self, choice_admin_fixture, csv_with_is_active):
        """Test importing choices with various is_active values"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(csv_with_is_active)

        initial_count = Choice.objects.count()
        success, message = admin.import_csv_data(csv_file)

        assert success is True
        assert Choice.objects.count() == initial_count + 4

        # Verify is_active values were set correctly
        active_choice = Choice.objects.get(model="activity.event", field="status", value="active")
        assert active_choice.is_active is True

        inactive_choice = Choice.objects.get(model="activity.event", field="status", value="inactive")
        assert inactive_choice.is_active is False

        # Test numeric boolean values
        pending_choice = Choice.objects.get(model="activity.event", field="status", value="pending")
        assert pending_choice.is_active is True

        archived_choice = Choice.objects.get(model="activity.event", field="status", value="archived")
        assert archived_choice.is_active is False

    def test_import_updates_is_active(self, choice_admin_fixture, csv_with_update):
        """Test that import can update is_active status"""
        admin = choice_admin_fixture.admin

        # Create initial choices - both active
        Choice.objects.create(
            model="activity.eventtype",
            field="wildlifesighting_species",
            value="elephant",
            display="Elephant",
            is_active=True,
        )
        Choice.objects.create(
            model="activity.eventtype", field="wildlifesighting_species", value="rhino", display="Rhino", is_active=True
        )

        csv_file = io.StringIO(csv_with_update)
        success, message = admin.import_csv_data(csv_file)

        assert success is True

        # Verify elephant is still active and rhino is now inactive
        elephant = Choice.objects.get(model="activity.eventtype", field="wildlifesighting_species", value="elephant")
        assert elephant.is_active is True

        rhino = Choice.objects.get(model="activity.eventtype", field="wildlifesighting_species", value="rhino")
        assert rhino.is_active is False

    def test_import_default_is_active_when_omitted(self, choice_admin_fixture):
        """Test that is_active defaults to True when column is omitted"""
        admin = choice_admin_fixture.admin
        csv_content = """model,field,value,display,icon,ordernum
activity.event,priority,urgent,Urgent Priority,,1"""
        csv_file = io.StringIO(csv_content)

        success, message = admin.import_csv_data(csv_file)

        assert success is True

        # Verify is_active defaults to True
        choice = Choice.objects.get(model="activity.event", field="priority", value="urgent")
        assert choice.is_active is True

    def test_import_invalid_is_active_value(self, choice_admin_fixture, csv_with_invalid_is_active):
        """Test that invalid is_active values are caught"""
        admin = choice_admin_fixture.admin
        csv_file = io.StringIO(csv_with_invalid_is_active)

        success, message = admin.import_csv_data(csv_file)

        assert success is False
        assert "is_active" in message.lower()
        assert "boolean" in message.lower()


@pytest.mark.usefixtures("tenant_settings")
class TestCSVTemplateDownload:
    """Test CSV template download from import page"""

    def test_csv_fields_match_export_fields(self, choice_admin_fixture):
        """Test that CSV import uses fields from fields_to_export"""
        admin = choice_admin_fixture.admin
        required_fields, optional_fields, all_fields = admin._get_csv_field_info()

        # Verify that all_fields is derived from fields_to_export
        # (excluding sub_choice_of, which is export-only, and delete-now, which is intentionally hidden from users
        # and only available for advanced/undocumented import use cases)
        expected_fields = [f for f in admin.fields_to_export if f not in ["sub_choice_of", "delete-now"]]
        assert all_fields == expected_fields

        # Verify required fields
        assert required_fields == ["model", "field", "value"]

        # Verify optional fields don't include required ones, sub_choice_of, or delete-now
        for field in optional_fields:
            assert field not in required_fields
            assert field != "sub_choice_of"
            assert field != "delete-now"

    def test_download_csv_template_from_import_page(self, choice_admin_fixture, client):
        """Test downloading CSV template from import page"""
        user = choice_admin_fixture.user
        client.force_login(user)

        # Access the template download via GET parameter on import page
        response = client.get("/admin/choices/choice/import-csv/?download_template=1")

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        # The filename uses the model name (singular: "choice")
        assert "choice_import_template.csv" in response["Content-Disposition"]

        # Check the content using CSV reader for proper parsing
        content = response.content.decode("utf-8")
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)

        # Should have header row and one example row
        assert len(rows) == 2

        # Check headers
        headers = rows[0]
        assert "model" in headers
        assert "field" in headers
        assert "value" in headers
        assert "display" in headers
        assert "icon" in headers
        assert "ordernum" in headers
        assert "is_active" in headers

        # Check example row
        example_row = rows[1]
        assert "activity.event" in example_row
        assert "priority" in example_row
        assert "high" in example_row
        assert "true" in example_row


@pytest.mark.usefixtures("tenant_settings")
class TestCSVImportView:
    """Test the admin view for CSV import"""

    def test_import_view_get(self, choice_admin_fixture, client):
        """Test GET request shows import form"""
        user = choice_admin_fixture.user
        client.force_login(user)

        response = client.get("/admin/choices/choice/import-csv/")

        assert response.status_code == 200
        assert b"csv_file" in response.content or b"Upload" in response.content

    def test_import_view_post_success(self, choice_admin_fixture, client, valid_csv_content):
        """Test POST request with valid CSV imports data"""
        user = choice_admin_fixture.user
        client.force_login(user)

        csv_file = io.StringIO(valid_csv_content)
        csv_file.name = "choices.csv"

        initial_count = Choice.objects.count()
        response = client.post("/admin/choices/choice/import-csv/", {"csv_file": csv_file})

        # Should redirect after success
        assert response.status_code in [200, 302]
        assert Choice.objects.count() > initial_count

    def test_import_view_post_validation_error(self, choice_admin_fixture, client, invalid_csv_missing_required):
        """Test POST request with invalid CSV shows errors"""
        user = choice_admin_fixture.user
        client.force_login(user)

        csv_file = io.StringIO(invalid_csv_missing_required)
        csv_file.name = "choices.csv"

        initial_count = Choice.objects.count()
        response = client.post("/admin/choices/choice/import-csv/", {"csv_file": csv_file})

        assert response.status_code == 200  # Shows form with errors
        assert Choice.objects.count() == initial_count  # No import

        # Check for error messages in content
        content = response.content.decode()
        assert "error" in content.lower() or "row" in content.lower()
