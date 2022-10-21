import logging
from functools import reduce

from django.contrib import admin as django_admin
from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.actions import delete_selected
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import (NestedObjects, capfirst,
                                        get_deleted_objects, model_ngettext,
                                        quote, unquote)
from django.contrib.gis import admin
from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

import mapping.models as models
from core.openlayers import OSMGeoExtendedAdmin
from mapping.esri_integration import arcgis_integration, update_db_groups
from mapping.forms import (ArcgisConfigurationForm, DisplayCategoryForm,
                           MapCenterForm, SpatialFeatureGroupStaticForm,
                           SpatialFeatureTypeForm, TileLayerFormWithAttributes)
from mapping.tasks import load_spatial_features_from_files
from mapping.utils import clear_features, construct_url_param

logger = logging.getLogger(__name__)


@admin.register(models.Map)
class MapAdmin(OSMGeoExtendedAdmin):
    form = MapCenterForm
    gis_geometry_field_name = 'center'


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    ordering = ('ordernum', 'name')
    list_display = ('name', 'ordernum', 'get_attributes')
    list_editable = ('ordernum',)
    form = TileLayerFormWithAttributes
    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('id', 'name',))
        }
        ),
        ('Tile Layer Attributes', {
            'classes': ('wide',),
            'fields': (('type', 'title', 'url', 'icon_url', 'configuration'))
        }
        ),
        ('Advanced Tile Layer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('attributes', 'created_at', 'updated_at',)
        })
    )
    readonly_fields = ('id', 'created_at', 'updated_at',)
    list_per_page = 25

    def get_attributes(self, instance):
        context = dict((k, instance.attributes[k]) for k in (
            'type', 'title', 'url', 'configuration') if k in instance.attributes)

        return mark_safe(''.join('<p><strong>{}</strong>: {}</p>'.format(escape(k), escape(v))
                                 for k, v in context.items()))

    get_attributes.short_description = _('Tile Layer Attributes (TileJSON)')


class BaseFeatureAdmin(OSMGeoExtendedAdmin):
    list_filter = ('type', 'featureset', 'spatialfile__name')
    list_display = ('name', 'type', 'featureset', 'get_spatialfile')
    ordering = ('name', 'type', 'featureset')
    search_fields = ('name', )

    def get_spatialfile(self, obj):
        return obj.spatialfile.name if obj.spatialfile else ""

    get_spatialfile.short_description = 'Spatial File'


# class SpatialFeatureTypeInline(admin.TabularInline):
#     model = models.SpatialFeatureType
#     ordering = ('name',)


class SpatialFeaturesInline(admin.TabularInline):
    model = models.SpatialFeatureGroupStatic.features.through
    form = SpatialFeatureGroupStaticForm
    model._meta.verbose_name_plural = "Member of feature groups"
    extra = 1
    verbose_name = "Feature Group"


@admin.register(models.DisplayCategory)
class DisplayCategoryAdmin(admin.ModelAdmin):
    ordering = ('name',)
    form = DisplayCategoryForm


@admin.register(models.SpatialFeatureGroupStatic)
class SpatialFeatureGroupStaticAdmin(admin.ModelAdmin):
    ordering = ('name',)
    search_fields = ('name',)
    autocomplete_fields = ('features',)


@admin.register(models.SpatialFeatureType)
class SpatialFeatureTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_visible', 'display_category')
    ordering = list_display
    search_fields = ('name',)
    list_filter = ('is_visible',)
    form = SpatialFeatureTypeForm
    fieldsets = (
        (None, {
            'fields': ('id', 'name', 'display_category', 'is_visible', 'presentation',)
        }),
        ('Advanced Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('tags', 'attribute_schema', 'provenance', 'external_id', 'external_source')
        })
    )


class GeometryTypeFilter(django_admin.SimpleListFilter):
    title = 'Geometry Type'
    parameter_name = 'geometry_type'

    def lookups(self, request, model_admin):
        return sorted((
            ('MULTILINESTRING', 'Multi-line String'),
            ('MULTIPOLYGON', 'Multi-polygon'),
            ('LINESTRING', 'Line String'),
            ('POLYGON', 'Polygon'),
            ('MULTIPOINT', 'Multi-point'),
            ('POINT', 'Point'),
        ), key=lambda item: item[1])

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(geometry_type=value)

        return queryset


@admin.register(models.SpatialFeature)
class SpatialFeatureAdmin(BaseFeatureAdmin):
    ordering = ('name', 'feature_type', 'external_source')
    list_display = ('name', 'feature_type',
                    'external_source', 'geometry_type', 'get_spatialfile')
    list_filter = (GeometryTypeFilter, 'feature_type',)
    search_fields = ('name', 'short_name', 'external_id', 'id')
    inlines = (
        SpatialFeaturesInline,
    )
    fieldsets = (
        (None, {
            'fields': ('id', 'name', 'feature_type', 'spatialfile', 'feature_geometry')
        }),
        ('Advanced Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('short_name', 'description', 'attributes', 'provenance', 'external_id', 'external_source')
        })
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(geometry_type=RawSQL(
            '''geometryType(feature_geometry)''', ()))
        return qs

    def geometry_type(self, obj):
        return obj.geometry_type
    geometry_type.short_description = 'Geometry Type'


def delete_selected_spatialfiles(modeladmin, request, queryset):
    opts = modeladmin.model._meta
    app_label = opts.app_label

    if not modeladmin.has_delete_permission(request):
        raise PermissionDenied

    deletable_objects, model_count, perms_needed, protected = get_deleted_objects(
        queryset, request, modeladmin.admin_site)

    spatial_features = models.SpatialFeature.objects.filter(
        reduce(lambda x, y: x | y, [Q(spatialfile=spatialfile) for spatialfile in queryset]))
    model_count['spatial features'] = spatial_features.count()

    # The user has already confirmed the deletion.
    # Do the deletion and return None to display the change list view again.
    if request.POST.get('post') and not protected:
        if perms_needed:
            raise PermissionDenied
        n = queryset.count()

        if n:
            for obj in queryset:
                obj_display = str(obj)
                modeladmin.log_deletion(request, obj, obj_display)

            if 'delete_associated_features' in request.POST:
                spatial_features.delete()

            queryset.delete()

            modeladmin.message_user(request, _(
                "Successfully deleted %(count)d %(items)s.") % {
                "count": n,
                "items": model_ngettext(modeladmin.opts, n)
            }, messages.SUCCESS)
        # Return None to display the change list page again.
        return None

    objects_name = model_ngettext(queryset)

    if perms_needed or protected:
        title = _("Cannot delete %(name)s") % {"name": objects_name}
    else:
        title = _("Are you sure?")

    context = dict(
        modeladmin.admin_site.each_context(request),
        title=title,
        objects_name=str(objects_name),
        deletable_objects=[deletable_objects],
        model_count=dict(model_count).items(),
        queryset=queryset,
        perms_lacking=perms_needed,
        protected=protected,
        opts=opts,
        action_checkbox_name=helpers.ACTION_CHECKBOX_NAME,
        media=modeladmin.media,
    )

    request.current_app = modeladmin.admin_site.name

    # Display the confirmation page
    return TemplateResponse(
        request,
        modeladmin.delete_selected_confirmation_template
        or [
            "admin/%s/%s/delete_selected_confirmation.html" % (
                app_label, opts.model_name),
            "admin/%s/delete_selected_confirmation.html" % app_label,
            "admin/delete_selected_confirmation.html",
        ],
        context,
    )


class BaseSpatialFileAdmin(admin.ModelAdmin):
    delete_confirmation_template = "admin/delete_confirmation_template.html"
    delete_selected_confirmation_template = "admin/delete_selected_confirmation_template.html"

    class Meta:
        abstract = True

    def save_model(self, request, obj, form, change):
        feature_updated = False
        if change:
            # check for feature related attributes update
            for record in form.changed_data:
                if record not in ['name', 'description']:
                    feature_updated, change = True, False

        if feature_updated:
            # Clear features incase any feature related record is updated
            logger.info("Clearing features, loading features afresh...")
            clear_features(obj)

        if not change:
            # load features if a new object or feature attributes are updated
            transaction.on_commit(
                lambda: load_spatial_features_from_files.apply_async(args=(str(obj.id),)))

        super().save_model(request, obj, form, change)

    def _delete_view(self, request, object_id, extra_context):
        """The 'delete' admin view for this model."""
        opts = self.model._meta
        app_label = opts.app_label

        to_field = request.POST.get(
            TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField(
                "The field %s cannot be referenced." % to_field)

        obj = self.get_object(request, unquote(object_id), to_field)

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.
        (deleted_objects, model_count, perms_needed, protected) = get_deleted_objects(
            [obj], request, self.admin_site)

        # get related features
        spatial_features = models.SpatialFeature.objects.filter(
            spatialfile=obj)
        model_count['spatial features'] = spatial_features.count()

        if request.POST and not protected:  # The user has confirmed the deletion.
            if perms_needed:
                raise PermissionDenied

            obj_display = str(obj)
            attr = str(to_field) if to_field else opts.pk.attname
            obj_id = obj.serializable_value(attr)
            self.log_deletion(request, obj, obj_display)

            if 'delete_associated_features' in request.POST:
                spatial_features.delete()

            self.delete_model(request, obj)

            return self.response_delete(request, obj_display, obj_id)

        object_name = str(opts.verbose_name)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Are you sure?")

        context = dict(
            self.admin_site.each_context(request),
            title=title,
            object_name=object_name,
            object=obj,
            deleted_objects=deleted_objects,
            model_count=dict(model_count).items(),
            perms_lacking=perms_needed,
            protected=protected,
            opts=opts,
            app_label=app_label,
            preserved_filters=self.get_preserved_filters(request),
            is_popup=(IS_POPUP_VAR in request.POST or
                      IS_POPUP_VAR in request.GET),
            to_field=to_field,
        )
        context.update(extra_context or {})

        return self.render_delete_form(request, context)

    def get_actions(self, request):
        """Patch delete_selected to have our method running"""
        actions = super().get_actions(request)
        actions['delete_selected'] = (delete_selected_spatialfiles,
                                      'delete_selected',
                                      "Delete selected spatial files")
        return actions

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['id', 'file_type', 'status']
        return self.readonly_fields


@admin.register(models.SpatialFeatureFile)
class SpatialFeatureFileAdmin(BaseSpatialFileAdmin):
    list_display = ('id', 'name', 'file_type', 'description', 'feature_type')
    ordering = list_display
    list_filter = ('name',)
    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('file_type', 'id', 'name', 'description', 'data', 'feature_type', 'name_field', 'id_field',
                       'status')
        }),
        ('Shapefile Optional Attributes', {
            'classes': ('wide', 'shapefile',),
            'fields': ('layer_number',)
        }
        ),
        ('GeoJSON Optional Attributes', {
            'classes': ('wide', 'geojson',),
            'fields': ('feature_types_file',)
        }
        ),)
    readonly_fields = ('id', 'status',)

    class Media:
        js = ["admin/js/jquery.init.js", "base.js"]

    def response_add(self, request, obj, post_url_continue=None):
        if '_save' in request.POST:
            self.add_background_download_message(obj, request, 'added')
            return self.response_post_save_add(request, obj)
        else:
            return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if '_save' in request.POST:
            self.add_background_download_message(obj, request, 'changed')
            return self.response_post_save_change(request, obj)
        else:
            return super().response_change(request, obj)

    def add_background_download_message(self, obj, request, action):
        msg_dict = {
            'obj': format_html(
                f'<a href="{reverse("admin:mapping_spatialfeaturefile_change", args=(obj.id,))}">{obj}</a>'),
            'features': format_html(f'<a href="{reverse("admin:mapping_spatialfeature_changelist")}">features</a>'),
            'action': action
        }
        msg = format_html(
            _('The Feature Import File "{obj}" {action} successfully. Feature download in progress, check loaded {features} after a few minutes'),
            **msg_dict)
        self.message_user(request, msg, messages.SUCCESS)


@admin.register(models.ArcgisConfiguration)
class ArcgisConfigurationAdmin(admin.ModelAdmin):
    delete_confirmation_template = "admin/arcgis_delete_confirmation_template.html"
    delete_selected_confirmation_template = "admin/arcgis_delete_selected_confirmation_template.html"

    list_display = ('config_name', 'username', )
    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('last_download_time', 'config_name', 'username', 'password', 'search_text',
                       'disable_import_feature_class_presentation')
        }),
        ('ArcGIS Group', {
            'classes': ('wide', 'groups'),
            'fields': ('groups',)
        }),
        ('Optional Attributes', {
            'classes': ('collapse',),
            'fields': ('service_url', 'source', 'type_label', 'id_field', 'name_field',)
        }
        ),)
    readonly_fields = ('last_download_time',)
    form = ArcgisConfigurationForm

    def delete_model(self, request, obj):
        opts = self.model._meta
        if 'delete_config_and_associated_features' in request.POST:
            # Delete related arcgis item, that deletes the associated features
            deleted_items = models.ArcgisItem.objects.filter(
                arcgis_config=obj).delete()
            features_count = deleted_items[1].get('mapping.SpatialFeature', 0)
            messages.success(
                request,
                _('The %(name)s “%(obj)s” and %(features_count)d associated features deleted successfully.') % {
                    'name': opts.verbose_name, 'obj': str(obj), 'features_count': features_count
                }
            )
        models.ArcgisGroup.objects.filter(config_id=obj.id).delete()
        super().delete_model(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        response = super().response_delete(request, obj_display, obj_id)
        queued_msgs = messages.get_messages(request)._queued_messages
        if len(queued_msgs) > 1:
            queued_msgs.pop()
        return response

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions['delete_selected'] = (self.delete_selected_arcgisconfigs,
                                      'delete_selected',
                                      "Delete selected Feature Service Configurations")
        return actions

    def get_deleted_objects(self, objs, request):
        """
        Find all objects related to ``objs`` that should also be deleted
        """
        admin_site = self.admin_site
        try:
            obj = objs[0]
        except IndexError:
            return [], {}, set(), []
        else:
            using = router.db_for_write(obj._meta.model)
        collector = NestedObjects(using=using)
        collector.collect(objs)
        perms_needed = set()

        def get_url(item):
            opts = item._meta
            admin_url = reverse(
                '%s:%s_%s_change' % (admin_site.name, opts.app_label, opts.model_name), None, (quote(item.pk),))
            return format_html('{}: <a href="{}">{}</a>', capfirst(opts.verbose_name), admin_url, item)

        def format_callback(obj):
            model = obj.__class__
            has_admin = model in admin_site._registry
            opts = obj._meta

            no_edit_link = '%s: %s' % (capfirst(opts.verbose_name), obj)

            if has_admin:
                if not admin_site._registry[model].has_delete_permission(request, obj):
                    perms_needed.add(opts.verbose_name)
                config_url = get_url(obj)

                features_to_delete = []
                for arc_item in models.ArcgisItem.objects.filter(arcgis_config=obj):
                    features_to_delete.extend(
                        [get_url(ft) for ft in arc_item.features])
                return (config_url, features_to_delete) if features_to_delete else config_url
            else:
                return no_edit_link

        deletable_objects = collector.nested(format_callback)

        to_delete = []
        features_count = 0
        for deletable_obj in list(deletable_objects):
            if isinstance(deletable_obj, str):
                to_delete.append(deletable_obj)
            else:
                features_count = len(deletable_obj[1])
                to_delete.extend([obj for obj in deletable_obj])

        protected = [format_callback(obj) for obj in collector.protected]
        model_count = {model._meta.verbose_name_plural: len(
            objs) for model, objs in collector.model_objs.items()}
        model_count["Features"] = features_count

        return to_delete, model_count, perms_needed, protected

    def delete_selected_arcgisconfigs(self, modeladmin, request, queryset):
        features_count = 0

        deletable_objects, model_count, perms_needed, protected = modeladmin.get_deleted_objects(
            queryset, request)
        if request.POST.get('post') and not protected:
            if perms_needed:
                raise PermissionDenied
            n = queryset.count()
            if n:
                for obj in queryset:
                    obj_display = str(obj)
                    modeladmin.log_deletion(request, obj, obj_display)

                    if 'delete_config_and_associated_features' in request.POST:
                        # Delete related arcgis item, that deletes the associated features
                        deleted_items = models.ArcgisItem.objects.filter(
                            arcgis_config=obj).delete()
                        features_count = deleted_items[1].get(
                            'mapping.SpatialFeature', 0)
                    models.ArcgisGroup.objects.filter(
                        config_id=obj.id).delete()

                modeladmin.delete_queryset(request, queryset)
                del_msg = _("Successfully deleted %(count)d %(items)s and %(features_count)d features") % {
                    "count": n, "items": model_ngettext(modeladmin.opts, n), "features_count": features_count
                }
                modeladmin.message_user(request, del_msg, messages.SUCCESS)
            return None
        return delete_selected(modeladmin, request, queryset)

    def get_fieldsets(self, request, obj=None):
        if self.fieldsets:
            fieldsets = list(self.fieldsets)
            for item in fieldsets:
                if not obj and 'ArcGIS Group' in item:
                    fieldsets.pop(fieldsets.index(item))
            return tuple(fieldsets)
        return [(None, {'fields': self.get_fields(request, obj)})]

    def response_add(self, request, obj, post_url_continue=None):

        groups_found = arcgis_integration(request, obj)
        if self.arcgis_config(request) or not groups_found:
            preserved_filters = self.get_preserved_filters(request)
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': obj._meta},
                                                 request.path)

            params = {'config_name': obj.config_name,
                      'search_text': obj.search_text,
                      'username': obj.username}
            redirect_url = construct_url_param(redirect_url, params)
            return HttpResponseRedirect(redirect_url)
        else:
            obj.save()
            update_db_groups(groups_found, obj)
            return super().response_add(request, obj, post_url_continue=None)

    def response_change(self, request, obj):

        groups_found = arcgis_integration(request, obj)
        if self.arcgis_config(request) or not groups_found:
            return HttpResponseRedirect(request.path_info)
        else:
            obj.save()
            update_db_groups(groups_found, obj)
            return super().response_change(request, obj)

    def save_model(self, request, obj, form, change):
        pass

    def arcgis_config(self, request):
        return any(x in request.POST for x in ["_testconnection", "_downloadfeatures"])

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'groups':
            object_id = request.resolver_match.kwargs.get('object_id')
            if object_id:
                obj = self.model.objects.get(id=int(object_id))
                kwargs['queryset'] = models.ArcgisGroup.objects.filter(
                    config_id=obj.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
