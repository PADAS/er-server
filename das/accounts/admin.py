import copy
import json

from django_multitenant.utils import get_current_tenant
from oauth2_provider.models import (
    get_access_token_admin_class,
    get_access_token_model,
    get_application_model,
    get_grant_admin_class,
    get_grant_model,
    get_refresh_token_admin_class,
    get_refresh_token_model,
)

import django.contrib.auth.models
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.main import IncorrectLookupParameters
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import re_path
from django.utils.crypto import get_random_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from accounts.account_linker import send_idp_invitation_email, send_idp_upgrade_email
from accounts.models import PermissionSet, User
from accounts.utils import patrol_mgmt_permissions
from activity.models import AlertRule
from core.admin import (
    BaseModelAdminMixin,
    CustomM2MChecks,
    ModelAdminDisplayingManyToManyFieldMixin,
)
from core.common import TIMEZONE_USED
from observations.models import Subject
from utils.admin import DefaultFilterMixin, FieldSetElementMixin
from utils.html import make_html_list
from utils.tenant import get_tenant_settings

from .forms import (
    AccessGrantForm,
    CustomUserCreationForm,
    KmkMasterLinkForm,
    PermissionSetAdminForm,
    RefreshForm,
    UserAdditionalForm,
)

Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()
AccessTokenAdmin = get_access_token_admin_class()
GrantAdmin = get_grant_admin_class()
RefreshTokenAdmin = get_refresh_token_admin_class()


@admin.register(PermissionSet)
class PermissionSetAdmin(ModelAdminDisplayingManyToManyFieldMixin, DjangoGroupAdmin):
    checks_class = CustomM2MChecks
    form = PermissionSetAdminForm
    list_display = ("name", "all_permissions", "all_users")
    ordering = ("name",)
    filter_horizontal = ("permissions", "children")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "permissions",
                )
            },
        ),
        (_("Acquire permissions from"), {"fields": ("acquire_from",)}),
        (_("Grant permissions to"), {"fields": ("children", "user_set")}),
    )

    def get_queryset(self, request):
        queryset = PermissionSet.objects.all()
        if not get_tenant_settings().env_settings.patrol_enabled:
            queryset = queryset.exclude(permissions__in=patrol_mgmt_permissions())

        # Prefetch the columns rendered by all_permissions / all_users on the
        # changelist. Without this, each row triggers its own SELECT for the
        # tenant-filtered permissions and the user_set, turning a 46-row page
        # into ~92 round-trips.
        #
        # The permissions prefetch needs the explicit tenant filter because
        # instance.permissions.all() bypasses tenant-scoping on the through
        # table (see all_permissions for the long-form note). `.distinct()`
        # is load-bearing: Django's M2M prefetch adds its own
        # `permission_sets__in=<page>` filter on top of our
        # `permission_sets__das_tenant=...` filter, and each `.filter()`
        # against a multi-valued relation gets a separate JOIN through the
        # through table. The cross-product fans out one row per matching
        # (other permissionset in the same tenant) pair, which renders as
        # duplicate permission rows in the changelist (ERA-10962 redux).
        tenant_permissions = Permission.objects.filter(permission_sets__das_tenant=get_current_tenant()).distinct()
        return queryset.prefetch_related(
            Prefetch("permissions", queryset=tenant_permissions, to_attr="_tenant_permissions"),
            "user_set",
        )

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "children":
            db_field.verbose_name = "Permission Sets"
        return super().formfield_for_dbfield(db_field, **kwargs)

    def all_permissions(self, instance):
        # instance.permissions.all() would return permissions across every
        # tenant — the M2M through table is tenant-scoped but the M2M relation
        # itself is not, so we must filter by current tenant. get_queryset
        # populates instance._tenant_permissions via Prefetch; fall back to
        # the live query for cases where this admin's get_queryset wasn't
        # used to load the instance. `.distinct()` collapses the
        # cross-product that arises because `instance.permissions` and
        # `permission_sets__das_tenant=...` each join through the through
        # table separately — without it, a permission held by N
        # PermissionSets in the same tenant renders N times.
        permissions = getattr(instance, "_tenant_permissions", None)
        if permissions is None:
            permissions = instance.permissions.filter(permission_sets__das_tenant=get_current_tenant()).distinct()
        return make_html_list(sorted(ps.name for ps in permissions))

    all_permissions.short_description = "Permissions"
    all_permissions.allow_tags = True

    def all_users(self, instance):
        users = instance.user_set.all()
        return make_html_list(sorted(u.get_full_name() for u in users))

    all_users.short_description = "Users"
    all_users.allow_tags = True

    class Media:
        css = {
            "all": ("css/resize_multipleselect_widget.css",),
        }


class UserAdmin(ModelAdminDisplayingManyToManyFieldMixin, DefaultFilterMixin, FieldSetElementMixin, DjangoUserAdmin):
    checks_class = CustomM2MChecks
    readonly_fields = ("_last_login", "_profiles", "_linked_subject_warning")
    ordering = (
        "username",
        "last_name",
        "first_name",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "role",
                    "email",
                    "phone",
                    "username",
                    "pin",
                    "password",
                    "_last_login",
                )
            },
        ),
        (
            "Advanced Attributes",
            {
                "classes": ("collapse",),
                "fields": (
                    "notes",
                    "expiry",
                    "moudatesigned",
                    "moutype",
                    "moufilename",
                    "organization",
                    "tech",
                ),
            },
        ),
        ("Additional Data", {"fields": ["additional"]}),
        (
            _("Permissions"),
            {
                "fields": (
                    "permission_sets",
                    "is_active",
                    "is_nologin",
                    "is_staff",
                    "is_superuser",
                    "act_as_profiles",
                    "_profiles",
                )
            },
        ),
        (
            _("Subject"),
            {
                "classes": ("collapse",),
                "fields": (
                    "linked_subject",
                    "_linked_subject_warning",
                ),
            },
        ),
    )

    list_display = ("display_name", "username", "_last_login", "member_permission_sets", "is_active")
    list_editable = ("is_active",)
    list_display_links = ("display_name",)
    list_filter = ("is_active", "is_staff", "is_superuser", "permission_sets")
    filter_horizontal = ("permission_sets",)
    form = UserAdditionalForm
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "role",
                    "email",
                    "phone",
                    "username",
                    "pin",
                )
            },
        ),
        (
            "Advanced Attributes",
            {
                "classes": ("collapse",),
                "fields": (
                    "notes",
                    "expiry",
                    "moudatesigned",
                    "moutype",
                    "moufilename",
                    "organization",
                    "tech",
                ),
            },
        ),
        ("Additional JSON Data", {"fields": ["additional"]}),
        (
            _("Password"),
            {
                "description": (
                    _("Optionally enter user's password," " otherwise a password reset email is sent to the" " user")
                ),
                "fields": (
                    "password1",
                    "password2",
                ),
            },
        ),
        (_("Permissions"), {"fields": ("permission_sets", "is_active", "is_nologin", "is_staff", "is_superuser")}),
        (_("User Profiles"), {"fields": ("act_as_profiles",)}),
        (
            _("Subject"),
            {
                "classes": ("collapse",),
                "fields": ("linked_subject",),
            },
        ),
    )

    def _idp_field_policy(self):
        """Identity-field policy for the current tenant: (require_idp, is_org_scoped).

        require_idp means the tenant is Auth0/IdP-backed; is_org_scoped means it
        is an Auth0 Organizations (org-enabled) site, where the username is
        itself a login identifier. Together they drive which identity fields the
        admin renders read-only or hinted.
        """
        feature_flags = get_tenant_settings().feature_flags
        org_id = feature_flags.idp_org_id
        return feature_flags.require_idp, bool(org_id and org_id.strip())

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        form.request_user = request.user
        if obj:
            form.current_user = obj
            require_idp, is_org_scoped = self._idp_field_policy()
            # On non-org IdP sites username stays editable; hint that it is the
            # user's ER username for this site (org sites lock it).
            # Mutating base_fields is per-request safe: ModelAdmin.get_form builds
            # a fresh form class per call and username is model-derived (not a
            # shared declared field), so this help_text does not leak across
            # requests.
            if require_idp and not is_org_scoped and "username" in form.base_fields:
                form.base_fields["username"].help_text = "User's EarthRanger username for this site."
        return form

    def _reset_button_state(self, obj):
        """Which password-reset control the change form should show, per the
        link/site/email matrix. Returns one of:

        - "live_reset"      non-Auth0 site: the normal Django reset link
        - "self_service"    linked account: user resets via Auth0 themselves
        - "resend"          unlinked, non-org, has email: (re)send the invitation
        - "needs_email"     unlinked, non-org, no email: add an email first
        - "contact_support" unlinked, org: provisioned out-of-band by support
        """
        require_idp, is_org_scoped = self._idp_field_policy()
        if not require_idp:
            return "live_reset"
        if obj is not None and obj.auth0_id:
            return "self_service"
        if is_org_scoped:
            return "contact_support"
        if obj is not None and obj.email:
            return "resend"
        return "needs_email"

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        # Tell the change-form template which password-reset control to render
        # for this account (live reset / self-service / resend invite / add-email
        # / contact support). The matching action views enforce the same policy.
        context["reset_button_state"] = self._reset_button_state(obj)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_default_filters(self, request):
        return {
            "is_active__exact": 1,
        }

    def get_fieldsets(self, request, obj=None):
        require_idp, _ = self._idp_field_policy()
        if not obj:
            fieldsets = super().get_fieldsets(request)
            if require_idp:
                # The password-set inputs are inert on IdP tenants: they are
                # optional (CustomUserCreationForm forces required=False) and
                # save_model overwrites any entered value via
                # set_unusable_password() on create. Drop the whole section that
                # carries them rather than show controls that do nothing.
                password_set_fields = {"password1", "password2"}
                fieldsets = tuple(
                    section for section in fieldsets if password_set_fields.isdisjoint(section[1].get("fields", ()))
                )
            return fieldsets

        fieldsets = copy.deepcopy(self.fieldsets)
        if require_idp:
            # Once the account is linked, email is read-only; render it through a
            # display field carrying the identity hint, since a read-only model
            # field would only show the model's own help text. Until linked, leave
            # the plain editable email field in place (it is the invitation target
            # and not yet an Auth0 identity).
            if obj.auth0_id:
                fieldsets[0][1]["fields"] = tuple(
                    "_email_with_idp_hint" if field == "email" else field for field in fieldsets[0][1]["fields"]
                )
            # The local password is not operative for these accounts and the
            # change-password view is blocked (see user_change_password), so drop
            # the password field — its read-only hash display and the "change
            # password" link it carries are both dead here. (Applies whether or
            # not the account is linked — login is always Auth0 on these sites.)
            fieldsets = self._remove_fields_from_fieldsets(
                fieldsets=fieldsets, field_to_remove="password", fieldset_index=0
            )
        if User.objects.filter(act_as_profiles__in=[obj]):
            fieldsets = self._remove_fields_from_fieldsets(
                fieldsets=fieldsets, field_to_remove="act_as_profiles", fieldset_index=3
            )
        else:
            fieldsets = self._remove_fields_from_fieldsets(
                fieldsets=fieldsets, field_to_remove="_profiles", fieldset_index=3
            )

        if Subject.objects.filter(linked_user=obj.pk).exists():
            fieldsets = self._remove_fields_from_fieldsets(
                fieldsets=fieldsets, field_to_remove="linked_subject", fieldset_index=4
            )
        else:
            fieldsets = self._remove_fields_from_fieldsets(
                fieldsets=fieldsets, field_to_remove="_linked_subject_warning", fieldset_index=4
            )

        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj is None:
            # The add form keeps identity fields editable so new accounts (and
            # their Auth0 identity) can be created.
            return readonly_fields
        require_idp, is_org_scoped = self._idp_field_policy()
        if require_idp and obj.auth0_id:
            # Once the account is linked (auth0_id set), the identity fields
            # mirror the user's Auth0 login identity, so they are read-only.
            # "email" must stay in readonly_fields: the admin form declares email
            # explicitly, and listing it here is what strips that declared field
            # from the form so a save cannot change it. get_fieldsets renders it
            # through _email_with_idp_hint, which carries the identity hint.
            readonly_fields = (*readonly_fields, "email", "_email_with_idp_hint")
            # On org-enabled (Auth0 Organizations) sites the username is itself a
            # valid Auth0 login identifier, so it is read-only once linked too.
            if is_org_scoped:
                readonly_fields = (*readonly_fields, "username")
        # Until linked, email and username stay editable — local values the admin
        # curates (email is the invitation target; username is what support will
        # provision into the Auth0 org on org-scoped sites).
        return readonly_fields

    def _email_with_idp_hint(self, instance):
        return format_html(
            '{}<br><span class="help">User\'s email address when they created their '
            "EarthRanger Identity account.</span>",
            instance.email or "",
        )

    _email_with_idp_hint.short_description = "Email"

    def display_name(self, instance):
        full_name = instance.get_full_name()
        if not full_name:
            full_name = instance.username
        return full_name

    display_name.admin_order_field = "username"

    def all_permission_sets(self, instance):
        pss = instance.get_all_permission_sets()
        return make_html_list(sorted(ps.name for ps in pss))

    all_permission_sets.short_description = "Effective Permission Sets"
    all_permission_sets.allow_tags = True

    def member_permission_sets(self, instance):
        pss = instance.permission_sets.all()
        return make_html_list(sorted(ps.name for ps in pss))

    member_permission_sets.short_description = "Member Permission Sets"
    member_permission_sets.allow_tags = True

    def user_change_password(self, request, id, form_url=""):
        require_idp, _ = self._idp_field_policy()
        if require_idp:
            # The local password is not operative on Auth0/IdP sites (login is
            # Auth0), so the admin password-change view must not set one — it is
            # the only path that would after account creation. This guard is
            # site-wide (require_idp), not scoped to linked (auth0_id) accounts.
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)

    def reset_password(self, request, user_id):
        require_idp, _ = self._idp_field_policy()
        if require_idp:
            # The Django password-reset email is a dead end on Auth0/IdP sites —
            # the new password never reaches Auth0. Block it site-wide
            # (require_idp, not scoped to linked accounts); the change form
            # surfaces the right path instead (self-service when linked, (re)send
            # invitation when unlinked — see _reset_button_state).
            raise PermissionDenied
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)

        if user.email:
            self._send_reset_email(request, user)
        return HttpResponseRedirect("..")

    def resend_idp_invitation(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)
        require_idp, is_org_scoped = self._idp_field_policy()
        # The magic-link invitation only helps an unlinked account on a common-DB
        # (non-org) IdP site that has an email to send to: linked accounts
        # self-serve via Auth0, org sites are provisioned out-of-band (the linker
        # rejects them), and there is nowhere to send without an email.
        if not (require_idp and not is_org_scoped and not user.auth0_id and user.email):
            raise PermissionDenied
        self._send_idp_invitation_email(request, user)
        return HttpResponseRedirect("..")

    def get_kml_master_link(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)
        if user.email:
            self.send_kml_email(request, user)
        return HttpResponseRedirect("..")

    def save_model(self, request, obj, form, change):
        should_notify_of_password_reset = False
        should_send_idp_email = False

        require_idp, is_org_scoped = self._idp_field_policy()
        if require_idp:
            # Org-scoped (Auth0 organization) sites invite users through Auth0
            # out-of-band, and account linking — where the magic link points —
            # already rejects them. Suppress the dead-end invitation email.
            should_send_idp_email = not change and bool(obj.email) and not is_org_scoped
            if not change:
                obj.set_unusable_password()
        else:
            if not change and (not form.cleaned_data["password1"] or not obj.has_usable_password()):
                # Django's PasswordResetForm won't let us reset an unusable
                # password. We set it above super() so we don't have to save twice.
                obj.set_password(get_random_string(length=12))
                should_notify_of_password_reset = bool(obj.email)

        if form.cleaned_data.get("linked_subject"):
            subject = form.cleaned_data["linked_subject"]
            if subject.linked_user != obj:
                subject.linked_user = obj
                subject.save()

        super(UserAdmin, self).save_model(request, obj, form, change)

        if should_send_idp_email:
            transaction.on_commit(lambda: self._send_idp_invitation_email(request, obj))
        if should_notify_of_password_reset:
            transaction.on_commit(lambda: self._send_reset_email(request, obj))

    @staticmethod
    def _send_idp_invitation_email(request, user):
        base_url = request.build_absolute_uri("/")
        if user.last_login:
            send_idp_upgrade_email(user, base_url=base_url)
        else:
            send_idp_invitation_email(user, base_url=base_url)

    @staticmethod
    def _send_reset_email(request, user):
        form = PasswordResetForm(data={"email": user.email})
        assert form.is_valid()

        opts = {
            "email_template_name": "registration/password_reset_email.html",
            "html_email_template_name": "registration/password_reset_email_html.html",
            "from_email": settings.DEFAULT_FROM_EMAIL,
            "request": request,
            "subject_template_name": "registration/password_reset_subject.txt",
            "use_https": request.is_secure(),
        }

        form.save(**opts)

    def send_kml_email(self, request, user):
        form = KmkMasterLinkForm(data={"email": user.email})
        assert form.is_valid()

        opts = {
            "request": request,
            "user": user,
            "subject_template_name": "utility/kml_master_link_subject.txt",
            "email_template_name": "utility/kml_master_link_email.html",
            "html_email_template_name": "utility/kml_master_link_email_html.html",
        }

        form.save(**opts)

    def get_urls(self):
        urls = super(UserAdmin, self).get_urls()
        my_urls = [
            re_path(
                r"^(.+)/change/reset-password/?$",
                self.admin_site.admin_view(self.reset_password),
            ),
            re_path(
                r"^(.+)/change/get-kml-link/?$",
                self.admin_site.admin_view(self.get_kml_master_link),
            ),
            re_path(
                r"^(.+)/change/resend-invitation/?$",
                self.admin_site.admin_view(self.resend_idp_invitation),
            ),
        ]
        return [*my_urls, *urls]

    def _last_login(self, instance):
        return instance.last_login if instance.last_login else "Never Logged in"

    def _profiles(self, instance):
        message = ""
        parents = [user.username for user in User.objects.filter(act_as_profiles__in=[instance])]
        if parents:
            notify_message = (
                "This user account is being used as a profile, and so it can not be assigned child profiles of its own."
            )
            message = mark_safe(f"{', '.join(parents)}<br/><br/> <b><i>{notify_message}</i></b>")
        return message

    _last_login.short_description = _("Last Login In %s" % TIMEZONE_USED)
    _last_login.admin_order_field = "last_login"

    _profiles.short_description = "Profile of"

    def _linked_subject_warning(self, instance):
        return mark_safe(
            f"<i>This user account is being used for the Subject: <b> {instance.linked_subject}</b>, "
            f"and can not assign any other Subject.</i>"
        )

    _linked_subject_warning.short_description = "Warning"

    def changelist_view(self, request, extra_context=None):
        """Override changelist_view to add alert rules data for JavaScript."""
        # Build the ChangeList ourselves to get the filtered, paginated
        # result_list without rendering the whole view. The previous
        # implementation called super().changelist_view twice — once to
        # discover the filtered queryset, then again with the extra_context
        # injected. That re-ran every per-admin sidebar query (e.g.
        # tracking SourceProviderConfigurationAdmin.has_add_permission),
        # the entire template, and admin app_dict assembly.
        try:
            cl = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            # Bad filter params; let the base view produce the standard
            # invalid-search response.
            return super().changelist_view(request, extra_context)

        queryset = cl.result_list
        extra_context = extra_context or {}

        user_ids_with_alerts = set(AlertRule.objects.filter(owner__in=queryset).values_list("owner_id", flat=True))

        user_alert_rules = {}
        form_index_to_user_id = {}
        for index, user in enumerate(queryset):
            form_index_to_user_id[str(index)] = str(user.id)
            user_alert_rules[str(user.id)] = {"has_alerts": user.id in user_ids_with_alerts}

        extra_context["user_alert_rules"] = json.dumps(user_alert_rules)
        extra_context["form_index_to_user_id"] = json.dumps(form_index_to_user_id)

        return super().changelist_view(request, extra_context)


admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)


class GrantAdmin(BaseModelAdminMixin):
    form = AccessGrantForm
    list_display = ("code", "application", "user", "expires")
    ordering = list_display
    raw_id_fields = ("user",)

    def _expires(self, o):
        return o.expires

    _expires.short_description = "expires in %s" % TIMEZONE_USED
    _expires.admin_order_field = "expires"


class AccessTokenAdmin(BaseModelAdminMixin):
    form = AccessGrantForm
    list_display = ("token", "user", "application", "_expires")
    ordering = ("token", "user", "application", "expires")
    raw_id_fields = ("user", "source_refresh_token")
    search_fields = (
        "user__username",
        "token",
    )

    def _expires(self, o):
        return o.expires

    _expires.short_description = "expires in %s" % TIMEZONE_USED
    _expires.admin_order_field = "expires"


class RefreshTokenAdmin(BaseModelAdminMixin):
    form = RefreshForm
    list_display = ("token", "user", "application", "_revoked")
    ordering = ("token", "user", "application", "revoked")
    raw_id_fields = ("user", "access_token")

    def _revoked(self, o):
        return o.revoked

    _revoked.short_description = "Revoked in %s" % TIMEZONE_USED
    _revoked.admin_order_field = "revoked"


# AccessToken
admin.site.unregister(AccessToken)
admin.site.register(AccessToken, AccessTokenAdmin)

# Grant
admin.site.unregister(Grant)
admin.site.register(Grant, GrantAdmin)

# Refresh
admin.site.unregister(RefreshToken)
admin.site.register(RefreshToken, RefreshTokenAdmin)
