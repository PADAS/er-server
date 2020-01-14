import logging
import time

from django.contrib.gis import admin
from django.templatetags.static import static
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages

import activity.models as models
from activity.forms import EventTypeForm, EventForm
from core.admin import InlineExtraDynamicMixin
from activity.forms import EventProviderForm, AlertRuleForm
from core.openlayers import OSMGeoExtendedAdmin
from activity.tasks import refresh_event_details_view, recreate_event_details_view
from core.common import TIMEZONE_USED

logger = logging.getLogger(__name__)


class EventRelationshipInline(admin.TabularInline):
    model = models.EventRelationship
    fk_name = 'from_event'


class EventDetailsInline(admin.TabularInline):
    model = models.EventDetails


@admin.register(models.Event)
class EventAdmin(OSMGeoExtendedAdmin):
    # openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    # wms_layer = 'terrain,overlay'
    # wms_url = 'http://tiles.maps.eox.at/wms/'
    form = EventForm

    list_display = ('serial_number', '_created_at', 'event_type',
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

    def _created_at(self, o):
        return o.created_at
    _created_at.short_description = 'created at %s' % TIMEZONE_USED
    _created_at.admin_order_field = 'created_at'

    resolve_event.short_description = "Resolve Selected Events(Reports)"


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):

    form = EventTypeForm
    ordering = ('category', 'ordernum', 'display',)
    list_filter = ('category',)
    list_display = ('display', 'value', 'ordernum',
                    'category', 'is_collection', '_default_priority_display', '_icon_display', 'default_state')
    list_editable = ('ordernum', 'default_state',)
    list_display_links = ('display',)
    search_fields = ('display', 'value',)

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
        form.request = request
        return form

    def get_event_source_link(self, object_id):

        try:
            eventsource = models.EventSource.objects.get(
                event_type_id=object_id)
        except models.EventSource.DoesNotExist:
            return None
        else:
            return {
                'href': reverse(f'admin:{eventsource._meta.app_label}_{eventsource._meta.model_name}_change',
                                args=(eventsource.id,)),
                'display': eventsource.display
            }

    def change_view(self, request, object_id, form_url='', extra_context=None):

        extra_context = extra_context or {}
        extra_context['eventsource_ref'] = self.get_event_source_link(
            object_id)

        # if extra_context['eventsource_ref'] is not None:
        #     messages.add_message(request, messages.WARNING, "This Event Type is linked to an External Source. See the notice below for more details.")

        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url=form_url, extra_context=extra_context)


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

    def get_event_type_ref(self, object_id):

        try:
            eventsource = models.EventSource.objects.get(id=object_id)
            event_type = eventsource.event_type
        except models.EventSource.DoesNotExist:
            pass
        else:
            if event_type is not None:
                return {
                    'href': reverse(f'admin:{event_type._meta.app_label}_{event_type._meta.model_name}_change',
                                    args=(event_type.id,)),
                    'display': event_type.display
                }

    def change_view(self, request, object_id, form_url='', extra_context=None):

        extra_context = extra_context or {}
        extra_context['eventtype_ref'] = self.get_event_type_ref(object_id)
        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)


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
             'fields': ('provider_api', 'provider_username', 'provider_password', 'provider_token',
                        'icon_url', 'external_event_url',),
         }
         ),
        ('Advanced',
         {"classes": ('collapse',),
          'fields': ('additional', 'id',)
          }
         )
    )

    form = EventProviderForm


# @admin.register(models.EventsourceEvent)
# class EventsourceEventAdmin(admin.ModelAdmin):
#     pass
#

@admin.register(models.EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = ('display', 'value', 'ordernum', 'flag', 'is_active')
    ordering = ('display', 'value', 'ordernum', 'flag', 'is_active')


@admin.register(models.AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    readonly_fields = ('id', )  # 'conditions', 'schedule',)
    list_display = ('owner_username', 'title', 'is_active', 'ordernum',)
    form = AlertRuleForm
    list_filter = ('owner', 'is_active',)
    search_fields = ('title',)
    list_editable = ('is_active',)

    fieldsets = (
        (None, {
            'fields': ('owner', 'title', 'is_active', 'ordernum', )
        }
        ),
        ('Notifications',
         {
             "classes": ('wide',),
             'fields': ('notification_methods', 'event_types',),
         }
         ),
        ('Advanced',
         {"classes": ('collapse',),
          'fields': ('conditions', 'schedule', 'id',)
          }
         )
    )

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


@admin.register(models.RefreshRecreateEventDetailView)
class RefreshRecreateEventDetailViewAdmin(admin.ModelAdmin):
    # NOTE: This class relies on celery.

    change_list_template = 'admin/activity/eventtype/event_detail_change_list.html'
    list_display = ('performed_by', 'refresh_at',
                    'recreated_at', 'maintenance_status')

    enable_change_view = False

    def get_urls(self):
        urls = super().get_urls()
        from django.urls import path
        urls_paths = [
            path('re_create/', self.recreate_view),
            path('refresh/', self.refresh_view),
        ]
        return urls_paths + urls

    def has_add_permission(self, request):
        return False

    def manage_task_status(self, request, task, status, qs_method, name):
        action = 'Admin'

        while not task.ready():
            logger.info(f'State={task.state}, info={task.info}')
            time.sleep(0.5)

        if task.state == 'SUCCESS':
            qs_method(activity=action, status=status)
            self.message_user(
                request, f"Successfully {name} 'event_detail_view'")
        if task.state == 'FAILURE':
            qs_method(activity=action, status=task.state)
            self.message_user(
                request, f"Failed to {name} 'event_detail_view'", messages.ERROR)
        if task.state == 'RETRY':
            qs_method(activity=action, status=task.state)
            self.message_user(
                request, f"Retry again to {name} 'event_detail_view'",  messages.WARNING)

        return HttpResponseRedirect("../")

    def refresh_view(self, request):
        task = refresh_event_details_view.apply_async(args=('Admin',))
        status = self.model.REFRESH
        qs_method = self.model.objects.refresh
        name = 'refresh'
        return self.manage_task_status(request=request,
                                       task=task,
                                       status=status,
                                       qs_method=qs_method,
                                       name=name)

    def recreate_view(self, request):
        task = recreate_event_details_view.delay()
        status = self.model.SUCCESS
        qs_method = self.model.objects.recreate
        name = 'recreate'
        return self.manage_task_status(request=request,
                                       task=task,
                                       status=status,
                                       qs_method=qs_method,
                                       name=name)
