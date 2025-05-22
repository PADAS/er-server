import logging
from uuid import UUID

from oauth2_provider.admin import (
    AccessTokenAdmin,
    ApplicationAdmin,
    GrantAdmin,
    IDTokenAdmin,
    RefreshTokenAdmin,
)

from django.contrib import admin
from django.contrib.admin import widgets
from django.contrib.admin.checks import BaseModelAdminChecks
from django.contrib.admin.models import LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.db.models import QuerySet
from django.forms import HiddenInput
from django.forms.widgets import SelectMultiple
from django.utils.text import format_lazy
from django.utils.translation import gettext as _

from accounts.models import User
from core.models import (
    DASAccessToken,
    DASApplication,
    DASGrant,
    DASIDToken,
    DASRefreshToken,
)

logger = logging.getLogger("django.contrib.gis")


class ModelAdminHistoryViewHideSharedAdminUserRevisionsMixin(admin.ModelAdmin):
    """
    Mixin that overrides the history_view method of the ModelAdmin class to
    hide LogEntries from shared admin users that are initialized via fixtures.
    """

    def _get_queryset_log_entries_for_tenant(self, tenant_id: UUID, object_id: UUID) -> QuerySet:
        """
        Override the QuerySet for fetching the LogEntries for the given
        `tenant_id` and `object_id`.
        """
        # Fetch users that are part of the tenant
        users_in_tenant = User.objects.filter(das_tenant_id=tenant_id)
        return LogEntry.objects.filter(
            object_id=object_id,
            content_type=get_content_type_for_model(self.model),
            # Filter user ids that are part of the current tenant
            user_id__in=users_in_tenant,
        ).order_by("-action_time")

    def history_view(self, request, object_id, extra_context=None):
        """
        Override the `history_view` method to filter out log entries that are
        not part of the current tenant.
        """
        tenant_id = request.user.das_tenant_id
        action_list = self._get_queryset_log_entries_for_tenant(
            tenant_id=tenant_id,
            object_id=object_id,
        )
        extra_context = {"action_list": action_list}

        return super().history_view(
            request=request,
            object_id=object_id,
            extra_context=extra_context,
        )


class BaseModelAdminMixin(ModelAdminHistoryViewHideSharedAdminUserRevisionsMixin, admin.ModelAdmin):
    def get_form(self, request, obj=None, **kwargs):
        # exclude das_tenant from all admin forms
        if "widgets" in kwargs:
            kwargs["widgets"]["das_tenant"] = HiddenInput()
        else:
            kwargs["widgets"] = dict(das_tenant=HiddenInput())
        return super().get_form(request, obj, **kwargs)


class ModelAdminDisplayingManyToManyFieldMixin(admin.ModelAdmin):
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        db = kwargs.get("using")

        if "widget" not in kwargs:
            if db_field.name in self.filter_horizontal:
                kwargs["widget"] = widgets.FilteredSelectMultiple(db_field.verbose_name, False)
        if "queryset" not in kwargs:
            queryset = self.get_field_queryset(db, db_field, request)
            if queryset is not None:
                kwargs["queryset"] = queryset

        form_field = db_field.formfield(**kwargs)
        if isinstance(form_field.widget, SelectMultiple):
            msg = _("Hold down “Control”, or “Command” on a Mac, to select more than one.")
            help_text = form_field.help_text
            form_field.help_text = format_lazy("{} {}", help_text, msg) if help_text else msg

        return form_field


class HierarchyModelAdmin(ModelAdminDisplayingManyToManyFieldMixin, BaseModelAdminMixin):
    pass


class InlineExtraDynamicMixin:
    """
    This allows me to override the 'number of extra inline forms' depending on whether the
    containing object already exists.
    Inheriting class should include `extra` if the default is not desired.
    """

    extra = 1

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return self.extra


class SaveCoordinatesToCookieMixin:
    gis_geometry_field_name = "location"

    def get_single_coordinate_pair(self, coords):
        try:
            if not isinstance(coords[0], tuple):
                return coords
            return self.get_single_coordinate_pair(coords[0])
        except IndexError as ex:
            logger.exception(f"Get single coordinate pair failed with {ex}")
        return (0, 0)

    def set_coordinates_cookie(self, http_response, obj):
        coords = None
        try:
            geom = getattr(obj, self.gis_geometry_field_name)
            if geom:
                coords = geom.coords
        except AttributeError as ex:
            logger.exception(f"Failed to get GIS geometry attribute on this obj {obj}: {ex}")
        else:
            if coords:
                long, lat = self.get_single_coordinate_pair(coords)
                http_response.set_cookie("latitude", lat, max_age=365 * 24 * 60 * 60)
                http_response.set_cookie("longitude", long, max_age=365 * 24 * 60 * 60)
        return http_response


class CustomM2MChecks(BaseModelAdminChecks):
    def _check_field_spec_item(self, obj, field_name, label):
        return []  # This disables error admin.E013


oauth_admins = [
    {"model": DASAccessToken, "admin": AccessTokenAdmin},
    {"model": DASApplication, "admin": ApplicationAdmin},
    {"model": DASGrant, "admin": GrantAdmin},
    {"model": DASIDToken, "admin": IDTokenAdmin},
    {"model": DASRefreshToken, "admin": RefreshTokenAdmin},
]

for admin_obj in oauth_admins:

    class CustomAdmin(admin_obj["admin"], BaseModelAdminMixin):
        pass

    try:
        admin.site.unregister(admin_obj["model"])
    except admin.sites.NotRegistered:
        continue

    admin.site.register(admin_obj["model"], CustomAdmin)
