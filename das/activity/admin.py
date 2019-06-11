from django.contrib.gis import admin
import activity.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.forms import Textarea
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from core.admin import InlineExtraDynamicMixin

from activity.forms import EventProviderForm, AlertRuleForm


class EventRelationshipInline(admin.TabularInline):
    model = models.EventRelationship
    fk_name = 'from_event'


class EventDetailsInline(admin.TabularInline):
    model = models.EventDetails


@admin.register(models.Event)
class EventAdmin(admin.OSMGeoAdmin):
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    wms_layer = 'terrain,overlay'
    wms_url = 'http://tiles.maps.eox.at/wms/'

    list_display = ('serial_number', 'created_at', 'event_type',
                    'title', 'location', 'attributes',)
    readonly_fields = ('id', 'serial_number', 'created_at', 'updated_at')
    search_fields = ('title', 'serial_number')
    list_filter = ('state', 'event_type', )
    actions = ('resolve_event',)
    inlines = [
        EventDetailsInline,
        # EventRelationshipInline,
    ]

    fieldsets = (
        (None, {
            'fields': ('serial_number', 'title', 'event_type', 'event_time', 'end_time',)
        }),
        ('Advanced', {
            'classes': ('wide', 'collapse',),
            'fields': ('state', 'priority', 'location', 'id', 'created_at', 'updated_at',)
        })
    )

    def resolve_event(self, request, queryset):
        queryset.update(state=models.Event.SC_RESOLVED)

    resolve_event.short_description = "Resolve Selected Events(Reports)"


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventRelatedSubject)
class EventRelatedSubject(admin.ModelAdmin):
    ordering = ('event__id', 'subject')


# class AdminImageWidget(AdminFileWidget):
#     def render(self, name, value, attrs=None):
#         output = []
#         if value and getattr(value, "url", None):
#             image_url = value.url
#             file_name=str(value)
#             output.append(u' <a href="%s" target="_blank"><img src="%s" alt="%s" /></a> %s ' % \
#                 (image_url, image_url, file_name, _('Change:')))
#         output.append(super(AdminImageWidget, self).render(name, value, attrs))
#         return mark_safe(u''.join(output))


from activity.forms import EventTypeForm

from django.http.response import HttpResponseRedirect


@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):

    form = EventTypeForm
    ordering = ('category', 'ordernum', 'display',)
    list_filter = ('category',)
    list_display = ('display', 'value', 'ordernum',
                    'category', 'is_collection', '_default_priority_display', '_icon_display', 'default_state')
    list_editable = ('ordernum', 'default_state',)

    fieldsets = (
        (None, {
            'fields': ('display', 'value', 'category', 'is_collection', 'icon', 'ordernum', )
        }
        ),
        ('Default Values', {
            'fields': ('default_priority', 'default_state',)
        }
        ),
        ('Schema & Form Definition',
         {
             "classes": ('wide',),
             'fields': ('schema',),
         })
    )

    def _icon_display(self, obj):
        url = models.Event.marker_icon(
            obj.icon_id, models.Event.PRI_NONE, models.Event.SC_NEW)
        return mark_safe(f'<img src="{url}" style="height:2.5em" />')

    _icon_display.short_description = 'Icon'

    def _default_priority_display(self, obj):
        url = models.Event.marker_icon(
            obj.icon_id, obj.default_priority, models.Event.SC_NEW)
        priority_name = models.Event.PRIORITY_LABELS_MAP.get(
            obj.default_priority, models.Event.PRI_NONE)
        return mark_safe(f'<img src="{url}" style="max-height:2.5em" /><p>({priority_name})</p>')

    _default_priority_display.short_description = 'Default Priority'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form


@admin.register(models.EventClass)
class EventClassAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'display':
            formfield.widget = Textarea(attrs=formfield.widget.attrs)
        return formfield


@admin.register(models.EventFactor)
class EventFactorAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventSource)
class EventSourceAdmin(admin.ModelAdmin):
    list_display = ('display', 'eventprovider', 'event_type', 'is_active',)
    readonly_fields = ('external_event_type', 'id',)
    list_filter = ('eventprovider', 'is_active',)
    fieldsets = (
        (None, {
            'fields': ('display', 'event_type', 'is_active', 'eventprovider',)
        }),
        ('Advanced', {
            'fields': ('external_event_type', 'additional', 'id'),
            'classes': ('wide', 'collapse',)
        })
    )


class EventSourceInline(InlineExtraDynamicMixin, admin.TabularInline):
    fields = ('external_event_type', 'display',
              'event_type', 'is_active', 'additional',)
    model = models.EventSource


@admin.register(models.EventProvider)
class EventProviderAdmin(admin.ModelAdmin):
    list_display = ('display', 'owner', 'is_active',)
    readonly_fields = ('id',)

    # inlines = [EventSourceInline, ]
    #
    # fieldsets = (
    #     (None, {
    #         'fields': ('display', 'owner', 'is_active',)
    #     }),
    #     ('Advanced', {
    #         'fields': ('additional', 'id'),
    #         'classes': ('wide', 'collapse',)
    #     })
    # )

    fieldsets = (
        (None, {
            'fields': ('display', 'owner', 'is_active', )
        }
        ),
        ('Particulars',
         {
             "classes": ('wide',),
             'fields': ('provider_api', 'provider_username', 'provider_password', 'provider_token',),
         }
         ),
        ('Advanced',
         {"classes": ('collapse',),
          'fields': ('additional', 'id',)
          }
         )
    )

    form = EventProviderForm


@admin.register(models.EventsourceEvent)
class EventsourceEventAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventClassFactor)
class EventClassFactorAdmin(admin.ModelAdmin):
    list_display = ('class_display', 'factor_display', 'priority')
    ordering = ('eventclass__ordernum', 'eventfactor__ordernum')

    def class_display(self, instance):
        return instance.eventclass.display

    def factor_display(self, instance):
        return instance.eventfactor.display


@admin.register(models.EventRelationshipType)
class EventRelationshipTypeAdmin(admin.ModelAdmin):
    list_display = ('value',)


@admin.register(models.EventRelationship)
class EventRelationshipAdmin(admin.ModelAdmin):

    # def from_event_display(self, obj):
    #     return obj.from_event.id
    # from_event_display.short_description = 'From Event'
    # def to_event_display(self, obj):
    #     return obj.to_event_id
    # to_event_display.short_description = 'To Event'

    list_display = ('from_event', 'type', 'to_event', 'ordernum')
    ordering = ('from_event', 'type', 'ordernum')


@admin.register(models.AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('owner_username', 'title', 'is_active', 'ordernum',)
    form = AlertRuleForm

    def owner_username(self, instance):
        return instance.owner.username
    owner_username.short_description = _('Owner')


@admin.register(models.NotificationMethod)
class NotificationMethodAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('owner_username', 'method', 'value', 'is_active',)

    def owner_username(self, instance):
        return instance.owner.username
    owner_username.short_description = _('Owner')
