import pytest

from django.core.exceptions import ValidationError

from activity.models import (
    NOTIFICATION_METHOD_EMAIL,
    NOTIFICATION_METHOD_SMS,
    NOTIFICATION_METHOD_WHATSAPP,
    NotificationMethod,
)


@pytest.mark.django_db
class TestNotificationMethod:
    def test_valid_phone_number_sms(self, user):
        """Test that a valid phone number for SMS is accepted and formatted correctly"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_SMS, value="1(415) 555-2671")
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format
        assert notification.value == "+14155552671"
        assert notification.phone_number == "+14155552671"

    def test_valid_phone_number_whatsapp(self, user):
        """Test that a valid phone number for WhatsApp is accepted and formatted correctly"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_WHATSAPP, value="+1 415 555 2671")
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format
        assert notification.value == "+14155552671"
        assert notification.phone_number == "+14155552671"

    def test_invalid_phone_number_sms(self, user):
        """Test that an invalid phone number for SMS raises ValidationError"""
        notification = NotificationMethod(
            owner=user, method=NOTIFICATION_METHOD_SMS, value="123"  # Too short to be a valid phone number
        )
        with pytest.raises(ValidationError) as excinfo:
            notification.full_clean()
        assert "Invalid phone number format" in str(excinfo.value)
        assert notification.phone_number is None

    def test_invalid_phone_number_whatsapp(self, user):
        """Test that an invalid phone number for WhatsApp raises ValidationError"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_WHATSAPP, value="not-a-phone-number")
        with pytest.raises(ValidationError) as excinfo:
            notification.full_clean()
        assert "Invalid phone number format" in str(excinfo.value)
        assert notification.phone_number is None

    def test_email_not_affected_by_phone_validation(self, user):
        """Test that email notification method is not affected by phone validation"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_EMAIL, value="test@example.com")
        notification.full_clean()
        notification.save()

        # Email should remain unchanged
        assert notification.value == "test@example.com"
        assert notification.phone_number is None

    def test_international_phone_number(self, user):
        """Test that international phone numbers are handled correctly"""
        notification = NotificationMethod(
            owner=user, method=NOTIFICATION_METHOD_SMS, value="+44 20 7123 4567"  # UK number
        )
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format
        assert notification.value == "+442071234567"
        assert notification.phone_number == "+442071234567"

    def test_phone_number_with_extension(self, user):
        """Test that phone numbers with extensions are handled correctly"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_SMS, value="+1(415) 555-2671 ext. 123")
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format (extension is removed)
        assert notification.value == "+14155552671"
        assert notification.phone_number == "+14155552671"

    def test_phone_number_property_with_invalid_stored_value(self, user):
        """Test that phone_number property handles invalid stored values gracefully"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_SMS, value="invalid-number")
        notification.save()  # Save without validation

        # phone_number property should return None for invalid numbers
        assert notification.phone_number is None

    def test_phone_number_property_with_malformed_stored_value(self, user):
        """Test that phone_number property handles malformed stored values gracefully"""
        notification = NotificationMethod(owner=user, method=NOTIFICATION_METHOD_SMS, value="(415) 555-2671 ext. 123")
        notification.save()  # Save without validation

        # phone_number property should return None
        assert notification.phone_number is None

    def test_phone_number_without_plus_prefix(self, user):
        """Test that phone numbers without + prefix are handled correctly"""
        notification = NotificationMethod(
            owner=user, method=NOTIFICATION_METHOD_SMS, value="1(415) 555-2671"  # Missing + prefix
        )
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format with + prefix
        assert notification.value == "+14155552671"
        assert notification.phone_number == "+14155552671"

    def test_international_phone_number_without_plus_prefix(self, user):
        """Test that international phone numbers without + prefix are handled correctly"""
        notification = NotificationMethod(
            owner=user, method=NOTIFICATION_METHOD_SMS, value="44 20 7123 4567"  # UK number without + prefix
        )
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format with + prefix
        assert notification.value == "+442071234567"
        assert notification.phone_number == "+442071234567"

    def test_phone_number_with_whitespace(self, user):
        """Test that phone numbers with whitespace are handled correctly"""
        notification = NotificationMethod(
            owner=user, method=NOTIFICATION_METHOD_SMS, value="  1(415) 555-2671  "  # Extra whitespace
        )
        notification.full_clean()
        notification.save()

        # Should be formatted to E.164 format with + prefix
        assert notification.value == "+14155552671"
        assert notification.phone_number == "+14155552671"
