import pytest

from factories import ProviderFactory
from observations.forms import SourceProviderForm


@pytest.fixture
def provider(db):
    """Fixture to create a test provider"""
    return ProviderFactory.create(provider_key="test_provider", display_name="Test Provider")


@pytest.fixture
def base_form_data():
    """Fixture for base form data"""
    return {
        "provider_key": "test_provider",
        "display_name": "Test Provider",
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceProviderForm:
    """Test cases for SourceProviderForm validation"""

    def test_two_way_messaging_with_valid_config(self, provider, base_form_data):
        """Test that form validates when two_way_messaging is True and messaging_config has required fields"""
        form_data = {
            **base_form_data,
            "two_way_messaging": True,
            "messaging_config_0": "test_adapter",  # adapter_type
            "messaging_config_1": "http://test.com",  # url
            "messaging_config_2": "test_key",  # apikey (optional)
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid()

    def test_two_way_messaging_without_config(self, provider, base_form_data):
        """Test that form validates when two_way_messaging is False and messaging_config is empty"""
        form_data = {
            **base_form_data,
            "two_way_messaging": False,
            "messaging_config_0": "",  # adapter_type
            "messaging_config_1": "",  # url
            "messaging_config_2": "",  # apikey
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid()

    def test_two_way_messaging_with_missing_adapter_type(self, provider, base_form_data):
        """Test that form fails validation when two_way_messaging is True but adapter_type is missing"""
        form_data = {
            **base_form_data,
            "two_way_messaging": True,
            "messaging_config_0": "",  # missing adapter_type
            "messaging_config_1": "http://test.com",  # url
            "messaging_config_2": "test_key",  # apikey
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert not form.is_valid()
        assert "messaging_config" in form.errors

    def test_two_way_messaging_with_missing_url(self, provider, base_form_data):
        """Test that form fails validation when two_way_messaging is True but url is missing"""
        form_data = {
            **base_form_data,
            "two_way_messaging": True,
            "messaging_config_0": "test_adapter",  # adapter_type
            "messaging_config_1": "",  # missing url
            "messaging_config_2": "test_key",  # apikey
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert not form.is_valid()
        assert "messaging_config" in form.errors

    def test_two_way_messaging_with_missing_both_fields(self, provider, base_form_data):
        """Test that form fails validation when two_way_messaging is True but both adapter_type and url are missing"""
        form_data = {
            **base_form_data,
            "two_way_messaging": True,
            "messaging_config_0": "",  # missing adapter_type
            "messaging_config_1": "",  # missing url
            "messaging_config_2": "test_key",  # apikey
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert not form.is_valid()
        assert "messaging_config" in form.errors
