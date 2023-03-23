from django import forms
from django.conf import settings
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.translation import gettext_lazy as _

from accounts.models import PermissionSet, User
from accounts.utils import patrol_mgmt_permissions
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from observations import kmlutils
from utils.features import features
from utils.tenant import get_tenant_settings

from .utils import fetch_organization_choices, fetch_tech_choices

PATROL_ENABLED = settings.PATROL_ENABLED

ROLE_CHOICES = [
    ("", "Select One"),
    ("community-liaison-officer", _("Community Liaison Officer")),
    ("community-manager", _("Community Manager")),
    ("deployment-partner", _("EarthRanger Deployment Partner")),
    ("ecologist-scientist", _("Ecologist / Scientist")),
    ("ecology-manager", _("Ecology Manager")),
    ("gis-engineer", _("GIS Engineer")),
    ("hwc-liaison", _("HWC Liaison")),
    ("hwc-officer", _("HWC Officer")),
    ("it-admin-tech-support", _("IT Admin / Tech Support")),
    ("operations-coordinator", _("Operations Coordinator")),
    ("operations-manager", _("Operations Manager")),
    ("protected-area-manager", _("Protected Area Manager")),
    ("security-manager", _("Security Manager")),
    ("support-team", _("EarthRanger Support Team")),
    ("tech-partner", _("Tech Partner")),
]


class CustomUserCreationForm(JSONFieldFormMixin, UserCreationForm):
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False)
    pin = forms.CharField(
        label="PIN",
        required=False,
        help_text="Use 4 digit numbers.",
        widget=forms.TextInput(attrs={"max": "4", "type": "number"}),
    )

    # Additional JSON Fields
    notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea)
    expiry = forms.DateTimeField(required=False, label="Expiry", widget=AdminDateWidget())
    moudatesigned = forms.DateTimeField(required=False, label="MoU Date Signed", widget=AdminDateWidget())
    moutype = forms.CharField(required=False, label="MoU Type")
    moufilename = forms.CharField(required=False, label="MoU Filename")
    tech = forms.TypedMultipleChoiceField(
        widget=FilteredSelectMultiple(verbose_name="Tech Choices", is_stacked=False), required=False
    )
    organization = forms.ChoiceField(required=False, help_text="User Organization")
    role = forms.ChoiceField(required=False, label="Role", choices=ROLE_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = False
        self.fields["password2"].required = False
        self.fields["password1"].widget.attrs["autocomplete"] = "off"
        self.fields["password2"].widget.attrs["autocomplete"] = "off"
        self.fields["tech"].choices = fetch_tech_choices()
        self.fields["organization"].choices = fetch_organization_choices()

    class Meta:
        model = User
        json_fields = ("notes", "expiry", "moudatesigned", "moutype", "moufilename", "organization", "tech", "role")
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "username",
            "pin",
        ) + json_fields

    json_field = "additional"

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 or password2:
            password2 = super().clean_password2()
        return password2

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email.strip() == "":
            return None
        return email

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if pin:
            if not pin.isnumeric():
                raise ValidationError("The value should be four digits.")
            if len(pin) != 4:
                raise ValidationError("The size should be four digits.")
        return pin


class UserAdditionalForm(JSONFieldFormMixin, UserChangeForm):
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False)
    pin = forms.CharField(
        label="PIN",
        required=False,
        help_text="Use 4 digit numbers.",
        widget=forms.TextInput(attrs={"max": "4", "type": "number"}),
    )

    # Additional JSON Fields
    notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea)
    expiry = forms.DateTimeField(required=False, label=_("MoU Expires"), widget=AdminDateWidget())
    moudatesigned = forms.DateTimeField(required=False, label="MoU Date Signed", widget=AdminDateWidget())
    moutype = forms.CharField(required=False, label="MoU Type")
    moufilename = forms.CharField(required=False, label="MoU Filename")
    tech = forms.TypedMultipleChoiceField(
        widget=FilteredSelectMultiple(verbose_name="Tech Choices", is_stacked=False), required=False
    )
    organization = forms.ChoiceField(required=False, help_text="User Organization")
    role = forms.ChoiceField(required=False, label="Role", choices=ROLE_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tech"].choices = fetch_tech_choices()
        self.fields["organization"].choices = fetch_organization_choices()

    class Meta:
        model = User
        json_fields = ("notes", "expiry", "moudatesigned", "moutype", "moufilename", "organization", "tech", "role")
        json_date_fields = ("expiry", "moudatesigned")
        fields = ("first_name", "last_name", "email", "phone", "username") + json_fields

    json_field = "additional"

    def clean_email(self):
        # Set email value as None rather than blank string.
        # In comparison Blank string is considered as Unique.
        email = self.cleaned_data.get("email")
        if email.strip() == "":
            return None
        return email

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if pin:
            if not pin.isnumeric():
                raise ValidationError("The value should be four digits.")
            if len(pin) != 4:
                raise ValidationError("The size should be four digits.")
        return pin


class PermissionSetAdminForm(forms.ModelForm):
    filter_horizontal = ("permissions", "children")
    user_set = forms.ModelMultipleChoiceField(
        label="Users",
        queryset=User.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(verbose_name=_("Users"), is_stacked=False),
    )

    acquire_from = forms.ModelMultipleChoiceField(
        label="Permission Sets",
        queryset=PermissionSet.objects.all().order_by("name"),
        required=False,
        widget=FilteredSelectMultiple(verbose_name=_("Permission Sets"), is_stacked=False),
    )

    class Meta:
        model = PermissionSet
        fields = (
            "name",
            "permissions",
            "children",
            "user_set",
            "acquire_from",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["user_set"].initial = self.instance.user_set.all()
            self.fields["acquire_from"].initial = self.instance._parents.all()

        if not PATROL_ENABLED:
            self.fields["children"].queryset = self.fields["children"].queryset.exclude(
                permissions__in=patrol_mgmt_permissions()
            )

            self.fields["acquire_from"].queryset = self.fields["acquire_from"].queryset.exclude(
                permissions__in=patrol_mgmt_permissions()
            )

            self.fields["permissions"].queryset = self.fields["permissions"].queryset.exclude(
                codename__in=patrol_mgmt_permissions().values_list("codename")
            )

        self.fields["permissions"].queryset = self.fields["permissions"].queryset.exclude(
            codename__in=patrol_mgmt_permissions(
                modelnames=("patrolsegment", "patrolnote", "patrolfile", "patrolsegmentmembership")
            ).values_list("codename")
        )

    def _save_m2m(self):
        users = self.cleaned_data["user_set"]
        inherit_from = self.cleaned_data["acquire_from"]
        self.instance.user_set.set(users)
        self.instance._parents.set(inherit_from)
        return super()._save_m2m()


class KmkMasterLinkForm(forms.Form):
    email = forms.EmailField(label=_("Email"), max_length=254)

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        to_email,
        html_email_template_name=None,
    ):
        """
        Sends a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        if features.tms.is_on():
            from_email = get_tenant_settings().env_settings.default_from_email
            email_message = EmailMultiAlternatives(subject=subject, body=body, from_email=from_email, to=[to_email])
        else:
            email_message = EmailMultiAlternatives(subject=subject, body=body, to=[to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        email_message.send()

    def save(
        self,
        user=None,
        subject_template_name="registration/kml_master_link_subject.txt",
        email_template_name="registration/kml_master_link_email.html",
        request=None,
        html_email_template_name=None,
    ):
        context = {
            "kml_master_link": kmlutils.get_kml_master_link(user, request),
            "site_name": get_current_site(request).name,
        }
        self.send_mail(
            subject_template_name,
            email_template_name,
            context,
            user.email,
            html_email_template_name,
        )


class AccessGrantForm(forms.ModelForm):
    class Meta:
        labels = {"expires": f"Expires in {TIMEZONE_USED}"}


class RefreshForm(forms.ModelForm):
    class Meta:
        labels = {"revoked": f"Revoked in {TIMEZONE_USED}"}
