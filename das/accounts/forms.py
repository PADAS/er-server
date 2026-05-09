from django import forms
from django.conf import settings
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Permission
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from accounts.models import PermissionSet, User
from accounts.utils import (
    filter_permissions_by_tenant,
    get_profiles,
    patrol_mgmt_permissions,
)
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from observations import kmlutils
from observations.models import Subject
from utils.tenant import get_tenant_settings

from .mixins import UserFormValidatorMixin
from .utils import fetch_organization_choices, fetch_tech_choices

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


class RelatedFieldWidgetCanAdd(forms.widgets.Select):
    def __init__(self, related_model, related_url=None, *args, **kw):
        super(RelatedFieldWidgetCanAdd, self).__init__(*args, **kw)

        if not related_url:
            rel_to = related_model
            related_url = f"admin:{rel_to._meta.app_label}_{rel_to._meta.object_name.lower()}_add"

        self.related_url = related_url

    def render(self, name, value, *args, **kwargs):
        self.related_url = reverse(self.related_url)
        output = [super(RelatedFieldWidgetCanAdd, self).render(name, value, *args, **kwargs)]
        output.append(
            f'<a href="{self.related_url}?_to_field=id&_popup=1" class="add-another" '
            f'id="add_id_{name}" onclick="return showAddAnotherPopup(this);"> '
        )
        output.append(f'<img src="{settings.STATIC_URL}admin/img/icon-addlink.svg" alt="Add Another"/></a>')
        return mark_safe("".join(output))


class CustomUserCreationForm(UserFormValidatorMixin, JSONFieldFormMixin, UserCreationForm):
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
    act_as_profiles = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=FilteredSelectMultiple(verbose_name="Profiles", is_stacked=False),
        required=False,
    )
    linked_subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(linked_user=None),
        required=False,
        widget=RelatedFieldWidgetCanAdd(Subject),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = False
        self.fields["password2"].required = False
        self.fields["password1"].widget.attrs["autocomplete"] = "off"
        self.fields["password2"].widget.attrs["autocomplete"] = "off"
        self.fields["tech"].choices = fetch_tech_choices()
        self.fields["organization"].choices = fetch_organization_choices()
        if hasattr(self, "request_user") and self.request_user or hasattr(self, "current_user") and self.current_user:
            self.fields["act_as_profiles"].queryset = get_profiles(users=self._get_exclude_users())
        self.fields["linked_subject"].queryset = Subject.objects.filter(linked_user=None)

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
            "linked_subject",
        ) + json_fields

    json_field = "additional"


class UserAdditionalForm(UserFormValidatorMixin, JSONFieldFormMixin, UserChangeForm):
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
    act_as_profiles = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=FilteredSelectMultiple(verbose_name="Profiles", is_stacked=False),
        required=False,
    )
    linked_subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(linked_user=None),
        required=False,
        widget=RelatedFieldWidgetCanAdd(Subject),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tech"].choices = fetch_tech_choices()
        self.fields["organization"].choices = fetch_organization_choices()
        if hasattr(self, "request_user") and self.request_user or hasattr(self, "current_user") and self.current_user:
            self.fields["act_as_profiles"].queryset = get_profiles(users=self._get_exclude_users())
        self.fields["linked_subject"].queryset = Subject.objects.filter(linked_user=None)

    class Meta:
        model = User
        json_fields = ("notes", "expiry", "moudatesigned", "moutype", "moufilename", "organization", "tech", "role")
        json_date_fields = ("expiry", "moudatesigned")
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "username",
            "act_as_profiles",
            "linked_subject",
        ) + json_fields

    json_field = "additional"

    def clean(self):
        cleaned_data = super().clean()
        # Note: Alert rules validation moved to client-side warnings for better UX
        return cleaned_data


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
        # Re-evaluate tenant-scoped querysets here. The class-level
        # ModelMultipleChoiceField declarations above run at import time,
        # before the tenant middleware has set the threadlocal — so the
        # tenant manager would either raise or filter against the wrong
        # tenant. Reassigning in __init__ ensures the queryset is built
        # per-request with the correct tenant context.
        self.fields["user_set"].queryset = User.objects.all()
        self.fields["acquire_from"].queryset = PermissionSet.objects.all().order_by("name")

        if self.instance and self.instance.pk:
            self.fields["user_set"].initial = self.instance.user_set.all()
            self.fields["acquire_from"].initial = self.instance._parents.all()
            self.fields["permissions"].initial = self.instance.permissions.filter(
                permissionsetpermission__das_tenant_id=get_tenant_settings().id
            )

        # select_related("content_type") is required: Permission.__str__ renders
        # "{content_type} | {name}", and FilteredSelectMultiple iterates every
        # option to render the change form. Without the join, each rendered
        # option triggers its own SELECT on django_content_type — N+1 that
        # turns the admin page into an apparent hang on tenants with many
        # per-tenant event permissions. DjangoGroupAdmin.formfield_for_manytomany
        # adds the same hint upstream; we lose it because we reassign queryset.
        self.fields["permissions"].queryset = filter_permissions_by_tenant(
            tenant_settings=get_tenant_settings(),
            queryset=Permission.objects.select_related("content_type"),
        )

        if not get_tenant_settings().env_settings.patrol_enabled:
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
        email_message = EmailMultiAlternatives(
            subject=subject, body=body, from_email=settings.FROM_EMAIL, to=[to_email]
        )
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
