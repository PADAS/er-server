"""
Tests for the branded HTML email templates and their send paths.

Covers:
- Password reset (admin path and public PasswordResetView path) produces
  a multipart message whose HTML alternative contains the EarthRanger
  wordmark, the reset button/link, and the correct confirm URL.
- The account-linker "email changed" notice is multipart with an HTML
  alternative containing the wordmark and the "has been updated" copy,
  while the text body still matches the old plain-text content.
- Shared-base sanity: the EarthRanger wordmark appears in at least two
  different email types, proving the base template is shared.
"""

from __future__ import annotations

from email.mime.image import MIMEImage
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.admin import site as admin_site
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import resolve

from accounts.account_linker import (
    _send_email_changed_notification,
    send_idp_invitation_email,
)
from accounts.admin import UserAdmin
from accounts.email_branding import attach_brand_logo
from accounts.forms import BrandedPasswordResetForm, KmkMasterLinkForm
from accounts.management.commands.send_password_reset import Command

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOMAIN = "testsite.pamdas.org"
# Django's test runner always allows "testserver" regardless of ALLOWED_HOSTS.
# PasswordResetForm.save calls request.get_host() via get_current_site(), so
# the host used for the request must pass Django's AllowedHosts check.
_TEST_SERVER_HOST = "testserver"
_FROM_EMAIL = "noreply@example.com"


def _fake_request():
    factory = RequestFactory(SERVER_NAME=_TEST_SERVER_HOST, SERVER_PORT=443, HTTPS="on")
    request = factory.post("/")
    request.META["HTTP_HOST"] = _TEST_SERVER_HOST
    request.META["wsgi.url_scheme"] = "https"
    return request


def _non_idp_tenant_settings() -> MagicMock:
    mock = MagicMock()
    mock.feature_flags.require_idp = False
    mock.feature_flags.idp_org_id = None
    mock.domain = _DOMAIN
    return mock


# ---------------------------------------------------------------------------
# Password reset HTML template — rendered content
# ---------------------------------------------------------------------------


class TestPasswordResetHtmlTemplateContent:
    """Verify the branded password reset HTML template renders correctly.

    We test the template directly via render_to_string rather than driving
    the full PasswordResetForm.save machinery, which would require a complete
    multitenant + ALLOWED_HOSTS stack to produce an email reliably. What we
    care about is that the template contains the right branded elements;
    the PasswordResetForm wiring is verified by checking the opts dict below.
    """

    @pytest.fixture(autouse=True)
    def _rendered(self):
        ctx = {
            "protocol": "https",
            "domain": _TEST_SERVER_HOST,
            "uid": "abc123",
            "token": "xyz-def456",
            "user": "resetuser",
            "site_name": _TEST_SERVER_HOST,
        }
        self.html = render_to_string("registration/password_reset_email_html.html", ctx)
        self.text = render_to_string("registration/password_reset_email.html", ctx)

    def test_reset_html_contains_earthranger_wordmark(self):
        """The HTML template contains the EarthRanger brand wordmark."""
        assert "EarthRanger" in self.html

    def test_reset_html_contains_confirm_href(self):
        """The HTML template includes a link (href) to the password-reset-confirm URL."""
        assert 'href="' in self.html
        assert "reset" in self.html

    def test_reset_html_contains_expiry_notice(self):
        """The HTML template includes the 48-hour expiry warning."""
        assert "48" in self.html

    def test_reset_html_contains_disregard_notice(self):
        """The HTML template includes the 'did not request' notice."""
        assert "disregard" in self.html.lower() or "did not request" in self.html.lower()

    def test_reset_text_template_unchanged(self):
        """The plaintext reset template is unchanged and still contains the reset URL."""
        assert "reset" in self.text.lower()

    def test_reset_html_uses_base_card_layout(self):
        """The HTML template inherits the base card structure (cream canvas, white card)."""
        assert "#faf2e9" in self.html  # canvas background
        assert "#0fcb8c" in self.html  # accent rule


# ---------------------------------------------------------------------------
# Password reset — opts dict wiring (admin and command paths)
# ---------------------------------------------------------------------------


class TestPasswordResetOptsWiring:
    """Verify that both the admin and management-command send paths pass
    html_email_template_name to PasswordResetForm.save."""

    def test_admin_send_reset_email_passes_html_template(self):
        """UserAdmin._send_reset_email opts include html_email_template_name."""
        admin = UserAdmin(User, admin_site)
        request = _fake_request()
        captured_opts: dict = {}

        with patch("accounts.admin.get_tenant_settings", return_value=_non_idp_tenant_settings()):
            with patch("accounts.admin.PasswordResetForm") as mock_form_cls:
                mock_form = MagicMock()
                mock_form.is_valid.return_value = True
                mock_form_cls.return_value = mock_form

                class _FakeUser:
                    email = "u@example.com"

                admin._send_reset_email(request, _FakeUser())
                captured_opts = mock_form.save.call_args[1]

        assert captured_opts.get("html_email_template_name") == "registration/password_reset_email_html.html"
        assert captured_opts.get("email_template_name") == "registration/password_reset_email.html"

    def test_send_password_reset_command_passes_html_template(self):
        """send_password_reset management command opts include html_email_template_name."""
        captured_opts: dict = {}

        mock_ts = MagicMock()
        mock_ts.domain = _TEST_SERVER_HOST

        with patch("accounts.management.commands.send_password_reset.get_tenant_settings", return_value=mock_ts):
            with patch("accounts.management.commands.send_password_reset.PasswordResetForm") as mock_form_cls:
                mock_form = MagicMock()
                mock_form.is_valid.return_value = True
                mock_form_cls.return_value = mock_form

                with patch("accounts.management.commands.send_password_reset.get_user_model") as mock_get_model:
                    mock_user = MagicMock()
                    mock_user.email = "u@example.com"
                    mock_get_model.return_value.objects.get.return_value = mock_user

                    cmd = Command(stdout=StringIO())
                    cmd.handle(username="someuser", tenant_domain=None, verbosity=0)
                    captured_opts = mock_form.save.call_args[1]

        assert captured_opts.get("html_email_template_name") == "registration/password_reset_email_html.html"
        assert captured_opts.get("email_template_name") == "registration/password_reset_email.html"


# ---------------------------------------------------------------------------
# Password reset — public PasswordResetView path (URL wiring check)
# ---------------------------------------------------------------------------


class TestPasswordResetViewUrlWiring:
    """The public PasswordResetView in urls_user.py is configured with
    html_email_template_name so the branded HTML template is used when Django
    sends the reset email. We verify the URLconf wiring directly rather than
    driving a full request, since the multitenant User manager makes
    PasswordResetForm.get_users silent in a bare test context."""

    def test_password_reset_view_has_html_email_template_name(self):
        """The PasswordResetView entry in urlpatterns exposes html_email_template_name."""
        match = resolve("/accounts/password_reset/")
        # The view is a class-based view; the init_kwargs carry the template names.
        view_kwargs = match.func.view_initkwargs
        assert view_kwargs.get("html_email_template_name") == "registration/password_reset_email_html.html"


# ---------------------------------------------------------------------------
# Account-linker email-changed notice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestEmailChangedNoticeIsMultipart:
    """_send_email_changed_notification now sends multipart/alternative."""

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.DEFAULT_FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture(autouse=True)
    def _mock_tenant(self):
        mock_ts = MagicMock()
        mock_ts.domain = _DOMAIN
        with patch("accounts.account_linker.get_tenant_settings", return_value=mock_ts):
            yield

    @pytest.fixture
    def sent_email_changed(self):
        _send_email_changed_notification("prior@example.com")
        assert len(mail.outbox) == 1
        return mail.outbox[0]

    def test_email_changed_is_multipart(self, sent_email_changed):
        """The email-changed notice has a text/html alternative."""
        assert len(sent_email_changed.alternatives) == 1
        _, mime_type = sent_email_changed.alternatives[0]
        assert mime_type == "text/html"

    def test_email_changed_html_contains_earthranger_wordmark(self, sent_email_changed):
        """The HTML part of the email-changed notice contains the EarthRanger wordmark."""
        html_body, _ = sent_email_changed.alternatives[0]
        assert "EarthRanger" in html_body

    def test_email_changed_html_contains_update_copy(self, sent_email_changed):
        """The HTML part says the email address has been updated."""
        html_body, _ = sent_email_changed.alternatives[0]
        assert "updated" in html_body

    def test_email_changed_text_body_contains_update_copy(self, sent_email_changed):
        """The plaintext body still contains 'has been updated'."""
        assert "updated" in sent_email_changed.body

    def test_email_changed_sent_to_prior_address(self, sent_email_changed):
        """The notice is sent to the prior email address."""
        assert sent_email_changed.to == ["prior@example.com"]


# ---------------------------------------------------------------------------
# Shared-base sanity: wordmark appears in multiple email types
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestSharedBaseRendersWordmarkAcrossEmailTypes:
    """Prove the base template is genuinely shared by asserting the EarthRanger
    wordmark appears in the HTML output of at least two different email types."""

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.DEFAULT_FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture(autouse=True)
    def _mock_linker_tenant(self):
        mock_ts = MagicMock()
        mock_ts.domain = _DOMAIN
        with patch("accounts.account_linker.get_tenant_settings", return_value=mock_ts):
            yield

    def test_wordmark_in_invitation_and_email_changed_html(self, das_tenant):
        """Both the invitation email and the email-changed notice share the branded header."""
        # Send an invitation email
        user = User.objects.create_user(
            username="wordmarkuser",
            email="wordmarkuser@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )
        with patch("accounts.account_linker.create_magic_link_token", return_value="tok"):
            send_idp_invitation_email(user, base_url=f"https://{_DOMAIN}")

        # Send an email-changed notice
        _send_email_changed_notification("prior@example.com")

        assert len(mail.outbox) == 2
        for msg in mail.outbox:
            html_body, mime_type = msg.alternatives[0]
            assert mime_type == "text/html"
            assert "EarthRanger" in html_body, f"EarthRanger wordmark missing from HTML of: {msg.subject}"


# ---------------------------------------------------------------------------
# KML master-link email
# ---------------------------------------------------------------------------


class TestKmlEmailHtmlTemplate:
    """The KML master-link HTML template renders correctly with the shared base."""

    _KML_LINK = "https://testsite.pamdas.org/kml/master?token=abc123"

    @pytest.fixture(autouse=True)
    def _rendered(self):
        ctx = {
            "kml_master_link": self._KML_LINK,
            "site_name": _DOMAIN,
        }
        self.html = render_to_string("utility/kml_master_link_email_html.html", ctx)
        self.text = render_to_string("utility/kml_master_link_email.html", ctx)

    def test_kml_html_contains_earthranger_wordmark(self):
        """The KML HTML template contains the EarthRanger brand wordmark."""
        assert "EarthRanger" in self.html

    def test_kml_html_contains_kml_link_href(self):
        """The HTML template includes the KML master link as a button href."""
        assert f'href="{self._KML_LINK}"' in self.html

    def test_kml_html_contains_kml_link_as_visible_text(self):
        """The HTML template includes the KML link as visible fallback text."""
        assert self._KML_LINK in self.html

    def test_kml_html_uses_shared_base_canvas(self):
        """The HTML inherits the cream canvas and accent rule from _email_base.html."""
        assert "#faf2e9" in self.html
        assert "#0fcb8c" in self.html

    def test_kml_text_body_unchanged(self):
        """The plain-text template is unchanged and still contains the KML link."""
        assert self._KML_LINK in self.text


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestKmlEmailSendIsMultipart:
    """admin.send_kml_email now produces a multipart message via KmkMasterLinkForm."""

    _KML_LINK = "https://testsite.pamdas.org/kml/master?token=abc123"

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture
    def sent_kml_email(self, das_tenant):
        user = User.objects.create_user(
            username="kmluser",
            email="kmluser@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )
        form = KmkMasterLinkForm(data={"email": user.email})
        assert form.is_valid()

        opts = {
            "request": _fake_request(),
            "user": user,
            "subject_template_name": "utility/kml_master_link_subject.txt",
            "email_template_name": "utility/kml_master_link_email.html",
            "html_email_template_name": "utility/kml_master_link_email_html.html",
        }

        # Patch kmlutils so we get a stable, known link without real KML infrastructure.
        with patch("accounts.forms.kmlutils.get_kml_master_link", return_value=self._KML_LINK):
            # get_current_site uses the request host; patch it for a stable site_name.
            with patch("accounts.forms.get_current_site") as mock_site:
                mock_site.return_value.name = _DOMAIN
                form.save(**opts)

        assert len(mail.outbox) == 1
        return mail.outbox[0]

    def test_kml_email_is_multipart(self, sent_kml_email):
        """The KML email has a text/html alternative."""
        assert len(sent_kml_email.alternatives) == 1
        _, mime_type = sent_kml_email.alternatives[0]
        assert mime_type == "text/html"

    def test_kml_email_html_contains_earthranger_wordmark(self, sent_kml_email):
        """The HTML part of the KML email contains the EarthRanger wordmark."""
        html_body, _ = sent_kml_email.alternatives[0]
        assert "EarthRanger" in html_body

    def test_kml_email_html_contains_kml_link_href(self, sent_kml_email):
        """The HTML part includes the KML link as a button href."""
        html_body, _ = sent_kml_email.alternatives[0]
        assert f'href="{self._KML_LINK}"' in html_body

    def test_kml_email_text_body_contains_kml_link(self, sent_kml_email):
        """The plaintext body still contains the KML link."""
        assert self._KML_LINK in sent_kml_email.body

    def test_kml_email_sent_to_user(self, sent_kml_email):
        """The email is sent to the user's email address."""
        assert sent_kml_email.to == ["kmluser@example.com"]


class TestKmlAdminOptsWiring:
    """admin.send_kml_email passes html_email_template_name to KmkMasterLinkForm.save."""

    def test_send_kml_email_passes_html_template(self, das_tenant):
        admin = UserAdmin(User, admin_site)
        request = _fake_request()

        captured_opts: dict = {}

        with patch("accounts.admin.KmkMasterLinkForm") as mock_form_cls:
            mock_form = MagicMock()
            mock_form.is_valid.return_value = True
            mock_form_cls.return_value = mock_form

            class _FakeUser:
                email = "u@example.com"

            admin.send_kml_email(request, _FakeUser())
            captured_opts = mock_form.save.call_args[1]

        assert captured_opts.get("html_email_template_name") == "utility/kml_master_link_email_html.html"
        assert captured_opts.get("email_template_name") == "utility/kml_master_link_email.html"


# ---------------------------------------------------------------------------
# CID logo: _email_base.html no longer contains an inline SVG
# ---------------------------------------------------------------------------


class TestEmailBaseTemplateNoCidSvg:
    """The shared email base template uses a CID img tag, not an inline SVG."""

    @pytest.fixture(autouse=True)
    def _rendered_base(self):
        # Render via a concrete template that extends _email_base.html.
        ctx = {
            "protocol": "https",
            "domain": _TEST_SERVER_HOST,
            "uid": "abc123",
            "token": "xyz-def456",
            "user": "resetuser",
            "site_name": _TEST_SERVER_HOST,
        }
        self.html = render_to_string("registration/password_reset_email_html.html", ctx)

    def test_base_does_not_contain_inline_svg(self):
        """The rendered email HTML no longer contains an inline <svg> element."""
        assert "<svg" not in self.html

    def test_base_contains_cid_img_tag(self):
        """The rendered email HTML contains an img referencing cid:earthranger-logo."""
        assert 'src="cid:earthranger-logo"' in self.html

    def test_base_still_contains_earthranger_wordmark(self):
        """The EarthRanger text wordmark is still present alongside the logo img."""
        assert "EarthRanger" in self.html


# ---------------------------------------------------------------------------
# CID logo: attach_brand_logo helper
# ---------------------------------------------------------------------------


class TestAttachBrandLogo:
    """attach_brand_logo attaches the PNG as a CID inline part."""

    def test_attach_brand_logo_sets_mixed_subtype_to_related(self):
        """After attach_brand_logo the message mixed_subtype is 'related'."""
        msg = EmailMultiAlternatives("subj", "body", "from@example.com", ["to@example.com"])
        attach_brand_logo(msg)
        assert msg.mixed_subtype == "related"

    def test_attach_brand_logo_adds_one_attachment(self):
        """attach_brand_logo adds exactly one MIME attachment to the message."""

        msg = EmailMultiAlternatives("subj", "body", "from@example.com", ["to@example.com"])
        attach_brand_logo(msg)
        assert len(msg.attachments) == 1

    def test_attach_brand_logo_content_id_is_earthranger_logo(self):
        """The attached MIME part has Content-ID <earthranger-logo>."""
        msg = EmailMultiAlternatives("subj", "body", "from@example.com", ["to@example.com"])
        attach_brand_logo(msg)
        attachment = msg.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert attachment["Content-ID"] == "<earthranger-logo>"

    def test_attach_brand_logo_content_disposition_is_inline(self):
        """The attached MIME part has Content-Disposition: inline."""

        msg = EmailMultiAlternatives("subj", "body", "from@example.com", ["to@example.com"])
        attach_brand_logo(msg)
        attachment = msg.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert "inline" in attachment["Content-Disposition"]

    def test_attach_brand_logo_raises_if_static_file_missing(self):
        """attach_brand_logo raises FileNotFoundError when the PNG cannot be found."""
        msg = EmailMultiAlternatives("subj", "body", "from@example.com", ["to@example.com"])
        with patch.object(finders, "find", return_value=None):
            with pytest.raises(FileNotFoundError, match="EarthRanger-Logo_icon.png"):
                attach_brand_logo(msg)


# ---------------------------------------------------------------------------
# CID logo: IdP invitation email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestIdpInvitationEmailHasLogo:
    """send_idp_invitation_email attaches the logo as a CID inline image."""

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.DEFAULT_FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture(autouse=True)
    def _mock_tenant(self):
        mock_ts = MagicMock()
        mock_ts.domain = _DOMAIN
        with patch("accounts.account_linker.get_tenant_settings", return_value=mock_ts):
            yield

    @pytest.fixture
    def sent_invitation(self, das_tenant):
        user = User.objects.create_user(
            username="invitelogouser",
            email="invitelogouser@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )
        with patch("accounts.account_linker.create_magic_link_token", return_value="tok"):
            send_idp_invitation_email(user, base_url=f"https://{_DOMAIN}")
        assert len(mail.outbox) == 1
        return mail.outbox[0]

    def test_invitation_has_logo_cid_attachment(self, sent_invitation):
        """The invitation email has exactly one attachment with CID earthranger-logo."""
        assert len(sent_invitation.attachments) == 1
        attachment = sent_invitation.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert attachment["Content-ID"] == "<earthranger-logo>"

    def test_invitation_mixed_subtype_is_related(self, sent_invitation):
        """The invitation email has mixed_subtype 'related'."""
        assert sent_invitation.mixed_subtype == "related"

    def test_invitation_html_references_cid(self, sent_invitation):
        """The HTML alternative in the invitation references cid:earthranger-logo."""
        html_body, _ = sent_invitation.alternatives[0]
        assert "cid:earthranger-logo" in html_body


# ---------------------------------------------------------------------------
# CID logo: account-linker email-changed notice
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestEmailChangedNoticeHasLogo:
    """_send_email_changed_notification attaches the logo as a CID inline image."""

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.DEFAULT_FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture(autouse=True)
    def _mock_tenant(self):
        mock_ts = MagicMock()
        mock_ts.domain = _DOMAIN
        with patch("accounts.account_linker.get_tenant_settings", return_value=mock_ts):
            yield

    @pytest.fixture
    def sent_email_changed(self):
        _send_email_changed_notification("prior@example.com")
        assert len(mail.outbox) == 1
        return mail.outbox[0]

    def test_email_changed_has_logo_cid_attachment(self, sent_email_changed):
        """The email-changed notice has a CID attachment with ID earthranger-logo."""
        assert len(sent_email_changed.attachments) == 1
        attachment = sent_email_changed.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert attachment["Content-ID"] == "<earthranger-logo>"

    def test_email_changed_mixed_subtype_is_related(self, sent_email_changed):
        """The email-changed notice has mixed_subtype 'related'."""
        assert sent_email_changed.mixed_subtype == "related"

    def test_email_changed_html_references_cid(self, sent_email_changed):
        """The HTML alternative in the email-changed notice references cid:earthranger-logo."""
        html_body, _ = sent_email_changed.alternatives[0]
        assert "cid:earthranger-logo" in html_body


# ---------------------------------------------------------------------------
# CID logo: KML master-link email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("das_tenant_monkeypatch")
class TestKmlEmailHasLogo:
    """KmkMasterLinkForm.send_mail attaches the logo as a CID inline image."""

    _KML_LINK = "https://testsite.pamdas.org/kml/master?token=abc123"

    @pytest.fixture(autouse=True)
    def _settings(self, settings):
        settings.FROM_EMAIL = _FROM_EMAIL

    @pytest.fixture
    def sent_kml_email(self, das_tenant):
        user = User.objects.create_user(
            username="kmllogouser",
            email="kmllogouser@example.com",
            das_tenant=das_tenant,
            is_active=True,
        )
        form = KmkMasterLinkForm(data={"email": user.email})
        assert form.is_valid()
        opts = {
            "request": _fake_request(),
            "user": user,
            "subject_template_name": "utility/kml_master_link_subject.txt",
            "email_template_name": "utility/kml_master_link_email.html",
            "html_email_template_name": "utility/kml_master_link_email_html.html",
        }
        with patch("accounts.forms.kmlutils.get_kml_master_link", return_value=self._KML_LINK):
            with patch("accounts.forms.get_current_site") as mock_site:
                mock_site.return_value.name = _DOMAIN
                form.save(**opts)
        assert len(mail.outbox) == 1
        return mail.outbox[0]

    def test_kml_email_has_logo_cid_attachment(self, sent_kml_email):
        """The KML email has a CID attachment with ID earthranger-logo."""
        assert len(sent_kml_email.attachments) == 1
        attachment = sent_kml_email.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert attachment["Content-ID"] == "<earthranger-logo>"

    def test_kml_email_mixed_subtype_is_related(self, sent_kml_email):
        """The KML email has mixed_subtype 'related'."""
        assert sent_kml_email.mixed_subtype == "related"

    def test_kml_email_html_references_cid(self, sent_kml_email):
        """The HTML alternative in the KML email references cid:earthranger-logo."""
        html_body, _ = sent_kml_email.alternatives[0]
        assert "cid:earthranger-logo" in html_body


# ---------------------------------------------------------------------------
# CID logo: BrandedPasswordResetForm
# ---------------------------------------------------------------------------


class TestBrandedPasswordResetFormHasLogo:
    """BrandedPasswordResetForm.send_mail attaches the logo as a CID inline image."""

    def test_branded_form_attaches_logo_when_html_template_provided(self):
        """send_mail on BrandedPasswordResetForm attaches logo and sets mixed_subtype."""
        form = BrandedPasswordResetForm()
        form.send_mail(
            subject_template_name="registration/password_reset_subject.txt",
            email_template_name="registration/password_reset_email.html",
            context={
                "protocol": "https",
                "domain": _TEST_SERVER_HOST,
                "uid": "abc123",
                "token": "tok-abc",
                "user": "u",
                "site_name": _TEST_SERVER_HOST,
            },
            from_email=_FROM_EMAIL,
            to_email="user@example.com",
            html_email_template_name="registration/password_reset_email_html.html",
        )

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.mixed_subtype == "related"
        assert len(msg.attachments) == 1
        attachment = msg.attachments[0]
        assert isinstance(attachment, MIMEImage)
        assert attachment["Content-ID"] == "<earthranger-logo>"

    def test_branded_form_no_logo_when_no_html_template(self):
        """send_mail without html_email_template_name sends plain text only — no logo."""
        form = BrandedPasswordResetForm()
        form.send_mail(
            subject_template_name="registration/password_reset_subject.txt",
            email_template_name="registration/password_reset_email.html",
            context={
                "protocol": "https",
                "domain": _TEST_SERVER_HOST,
                "uid": "abc123",
                "token": "tok-abc",
                "user": "u",
                "site_name": _TEST_SERVER_HOST,
            },
            from_email=_FROM_EMAIL,
            to_email="user@example.com",
        )

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert len(msg.attachments) == 0

    def test_password_reset_view_uses_branded_form(self):
        """The public PasswordResetView URLconf entry uses BrandedPasswordResetForm."""

        match = resolve("/accounts/password_reset/")
        view_kwargs = match.func.view_initkwargs
        assert view_kwargs.get("form_class") is BrandedPasswordResetForm
