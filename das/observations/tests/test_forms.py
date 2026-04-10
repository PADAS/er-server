import pytest

from factories import ProviderFactory, SourceFactory
from observations.forms import SourceForm, SourceProviderForm


@pytest.fixture
def provider(db):
    """Fixture to create a test provider"""
    return ProviderFactory.create(provider_key="test_provider", display_name="Test Provider")


@pytest.fixture
def source(provider):
    """Fixture to create a test source"""
    return SourceFactory.create(provider=provider)


@pytest.fixture
def base_form_data():
    """Fixture for base form data"""
    return {
        "provider_key": "test_provider",
        "display_name": "Test Provider",
    }


@pytest.fixture
def base_source_form_data(source):
    """Fixture for base source form data"""
    return {
        "id": str(source.id),
        "manufacturer_id": source.manufacturer_id,
        "provider": source.provider_id,
        "source_type": source.source_type or "tracking-device",
        "model_name": source.model_name or "test-model",
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

    def test_two_way_messaging_with_missing_apikey(self, provider, base_form_data):
        """Test that form fails validation when two_way_messaging is True but apikey is missing"""
        form_data = {
            **base_form_data,
            "two_way_messaging": True,
            "messaging_config_0": "test_adapter",  # adapter_type
            "messaging_config_1": "http://test.com",  # missing url
            "messaging_config_2": "",  # apikey
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

    @pytest.mark.parametrize(
        "value",
        ["01:30", "1:00", "99:59", "999:59", "00:00"],
    )
    def test_lag_notification_threshold_valid_hhmm(self, provider, base_form_data, value):
        form_data = {**base_form_data, "lag_notification_threshold": value}
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid(), form.errors

    @pytest.mark.parametrize(
        "value",
        ["01:30:00", "1:00:59", "99:59:59", "00:00:00"],
    )
    def test_lag_notification_threshold_valid_hhmmss(self, provider, base_form_data, value):
        form_data = {**base_form_data, "lag_notification_threshold": value}
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid(), form.errors

    @pytest.mark.parametrize(
        "value",
        ["abc", "1:60", "1:2", "01:30:60", ":30", "01:", "1:30:5"],
    )
    def test_lag_notification_threshold_invalid(self, provider, base_form_data, value):
        form_data = {**base_form_data, "lag_notification_threshold": value}
        form = SourceProviderForm(data=form_data, instance=provider)
        assert not form.is_valid()
        assert "lag_notification_threshold" in form.errors

    @pytest.mark.parametrize(
        "field",
        [
            "silence_notification_threshold",
            "default_silent_notification_threshold",
        ],
    )
    def test_other_threshold_fields_invalid(self, provider, base_form_data, field):
        form_data = {**base_form_data, field: "abc"}
        form = SourceProviderForm(data=form_data, instance=provider)
        assert not form.is_valid()
        assert field in form.errors

    @pytest.mark.parametrize(
        "field",
        [
            "silence_notification_threshold",
            "default_silent_notification_threshold",
        ],
    )
    def test_other_threshold_fields_valid(self, provider, base_form_data, field):
        form_data = {**base_form_data, field: "01:30"}
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid(), form.errors

    def test_threshold_fields_empty_is_valid(self, provider, base_form_data):
        form_data = {
            **base_form_data,
            "lag_notification_threshold": "",
            "silence_notification_threshold": "",
            "default_silent_notification_threshold": "",
        }
        form = SourceProviderForm(data=form_data, instance=provider)
        assert form.is_valid(), form.errors


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceFormThresholdValidation:

    @pytest.mark.parametrize(
        "value",
        ["01:30", "1:00:59", "99:59:59", "00:00"],
    )
    def test_silence_notification_threshold_valid(self, source, base_source_form_data, value):
        form_data = {**base_source_form_data, "silence_notification_threshold": value}
        form = SourceForm(data=form_data, instance=source)
        assert form.is_valid(), form.errors

    @pytest.mark.parametrize(
        "value",
        ["abc", "1:60", "1:2", "01:30:60"],
    )
    def test_silence_notification_threshold_invalid(self, source, base_source_form_data, value):
        form_data = {**base_source_form_data, "silence_notification_threshold": value}
        form = SourceForm(data=form_data, instance=source)
        assert not form.is_valid()
        assert "silence_notification_threshold" in form.errors

    def test_silence_notification_threshold_empty_is_valid(self, source, base_source_form_data):
        form_data = {**base_source_form_data, "silence_notification_threshold": ""}
        form = SourceForm(data=form_data, instance=source)
        assert form.is_valid(), form.errors
