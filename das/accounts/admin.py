from oauth2_provider.admin import AccessTokenAdmin, GrantAdmin, RefreshTokenAdmin
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_grant_model,
    get_refresh_token_model,
)

import django.contrib.auth.models
from django.conf import settings
from django.conf.urls import re_path
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import PasswordResetForm
from django.core.exceptions import PermissionDenied
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from accounts.models import PermissionSet, User
from accounts.utils import patrol_mgmt_permissions
from core.common import TIMEZONE_USED
from utils.admin import DefaultFilterMixin
from utils.features import features
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

PATROL_ENABLED = settings.PATROL_ENABLED


@admin.register(PermissionSet)
class PermissionSetAdmin(DjangoGroupAdmin):
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
        queryset = super(PermissionSetAdmin, self).get_queryset(request)
        if not PATROL_ENABLED:
            return queryset.exclude(permissions__in=patrol_mgmt_permissions())
        return queryset

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "children":
            db_field.verbose_name = "Permission Sets"
        return super().formfield_for_dbfield(db_field, **kwargs)

    def all_permissions(self, instance):
        permissions = instance.permissions.all()
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


class UserAdmin(DefaultFilterMixin, DjangoUserAdmin):
    readonly_fields = ("_last_login",)
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
            {"fields": ("permission_sets", "is_active", "is_nologin", "is_staff", "is_superuser", "act_as_profiles")},
        ),
    )

    list_display = (
        "display_name",
        "username",
        "_last_login",
        "member_permission_sets",
        "all_permission_sets",
        "is_active",
    )
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
    )

    def get_default_filters(self, request):
        return {
            "is_active__exact": 1,
        }

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

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # TODO: for a user with is_nologin set, do not return a set of profiles
        if db_field.name == "act_as_profiles":
            queryset = User.objects.filter(is_staff=False)
            # queryset = queryset.filter(is_nologin=True)
            queryset = queryset.by_is_active()
            queryset = queryset.exclude(pk=request.user.pk)
            kwargs["queryset"] = queryset
        return super(UserAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def reset_password(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)

        if user.email:
            self.send_reset_email(request, user)
        return HttpResponseRedirect("..")

    def get_kml_master_link(self, request, user_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        user = get_object_or_404(self.model, pk=user_id)
        if user.email:
            self.send_kml_email(request, user)
        return HttpResponseRedirect("..")

    def save_model(self, request, obj, form, change):
        if not change and (not form.cleaned_data["password1"] or not obj.has_usable_password()):
            # Django's PasswordResetForm won't let us reset an unusable
            # password. We set it above super() so we don't have to save twice.
            obj.set_password(get_random_string(length=12))
            should_reset_password = True
        else:
            should_reset_password = False

        super(UserAdmin, self).save_model(request, obj, form, change)

        if should_reset_password and obj.email:
            self.send_reset_email(request, obj)

    def send_reset_email(self, request, user):
        form = PasswordResetForm(data={"email": user.email})
        assert form.is_valid()

        opts = {
            "use_https": request.is_secure(),
            "request": request,
            "subject_template_name": "registration/password_reset_subject.txt",
            "email_template_name": "registration/password_reset_email.html",
        }
        if features.tms.is_on():
            opts["from_email"] = get_tenant_settings().env_settings.default_from_email

        form.save(**opts)

    def send_kml_email(self, request, user):
        form = KmkMasterLinkForm(data={"email": user.email})
        assert form.is_valid()

        opts = {
            "request": request,
            "user": user,
            "subject_template_name": "utility/kml_master_link_subject.txt",
            "email_template_name": "utility/kml_master_link_email.html",
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
        ]
        return [*my_urls, *urls]

    def _last_login(self, instance):
        return instance.last_login if instance.last_login else "Never Logged in"

    _last_login.short_description = _("Last Login In %s" % TIMEZONE_USED)
    _last_login.admin_order_field = "last_login"


admin.site.register(User, UserAdmin)
if admin.site.is_registered(django.contrib.auth.models.Group):
    admin.site.unregister(django.contrib.auth.models.Group)


class GrantAdmin(admin.ModelAdmin):
    form = AccessGrantForm
    list_display = ("code", "application", "user", "expires")
    ordering = list_display
    raw_id_fields = ("user",)

    def _expires(self, o):
        return o.expires

    _expires.short_description = "expires in %s" % TIMEZONE_USED
    _expires.admin_order_field = "expires"


class AccessTokenAdmin(admin.ModelAdmin):
    form = AccessGrantForm
    list_display = ("token", "user", "application", "_expires")
    ordering = ("token", "user", "application", "expires")
    raw_id_fields = ("user",)
    search_fields = (
        "user__username",
        "token",
    )

    def _expires(self, o):
        return o.expires

    _expires.short_description = "expires in %s" % TIMEZONE_USED
    _expires.admin_order_field = "expires"


class RefreshTokenAdmin(admin.ModelAdmin):
    form = RefreshForm
    list_display = ("token", "user", "application", "_revoked")
    ordering = ("token", "user", "application", "revoked")
    raw_id_fields = ("user", "access_token")

    def _revoked(self, o):
        return o.revoked

    _revoked.short_description = "Revoked in %s" % TIMEZONE_USED
    _revoked.admin_order_field = "revoked"


Application = get_application_model()
Grant = get_grant_model()
AccessToken = get_access_token_model()
RefreshToken = get_refresh_token_model()

# AccessToken
admin.site.unregister(AccessToken)
admin.site.register(AccessToken, AccessTokenAdmin)

# Grant
admin.site.unregister(Grant)
admin.site.register(Grant, GrantAdmin)

# Refresh
admin.site.unregister(RefreshToken)
admin.site.register(RefreshToken, RefreshTokenAdmin)
