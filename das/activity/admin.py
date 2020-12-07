import logging
import time
import datetime
import pytz
from enum import Enum

from django.contrib.gis import admin
from django.templatetags.static import static
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.db.models import OuterRef, Subquery, F, Case, Q, When, Value, CharField
from django.contrib.auth import get_user_model
from django.contrib.admin import SimpleListFilter

import activity.models as models
from activity.forms import EventTypeForm, EventForm, PatrolTypeForm, PatrolForm
from core.admin import InlineExtraDynamicMixin
from activity.forms import EventProviderForm, AlertRuleForm
from core.openlayers import OSMGeoExtendedAdmin
from activity.tasks import refresh_event_details_view, recreate_event_details_view
from core.common import TIMEZONE_USED, AdminFeatureFlag

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

    list_display = ('serial_number', '_created_at', '_event_time', '_updated_at', 'event_type',
                    'title', '_latitude', '_longitude')
    ordering = ('serial_number', 'created_at', 'event_time', 'updated_at', 'event_type', 'title')
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

    def _created_at(self, o):
        return o.created_at
    _created_at.short_description = 'created at %s' % TIMEZONE_USED
    _created_at.admin_order_field = 'created_at'

    def _event_time(self, o):
        return o.event_time
    _event_time.short_description = 'event time %s' % TIMEZONE_USED
    _event_time.admin_order_field = 'event_time'

    def _updated_at(self, o):
        return o.updated_at
    _updated_at.short_description = 'updated at %s' % TIMEZONE_USED
    _updated_at.admin_order_field = 'updated_at'

    def _longitude(self, o):
        return round(o.location.x, 5) if o.location else None
    _longitude.short_description = _('Longitude')

    def _latitude(self, o):
        return round(o.location.y, 5) if o.location else None
    _latitude.short_description = _('Latitude')



@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    ordering = ('name',)


@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):

    form = EventTypeForm
    ordering = ('display', 'value', 'ordernum', 'category', 'default_priority', 'default_state')
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
    ordering = list_display
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
    ordering = list_display
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
    ordering = ('owner', 'title', 'is_active', 'ordernum',)
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
    owner_username.admin_order_field = 'username'


@admin.register(models.NotificationMethod)
class NotificationMethodAdmin(admin.ModelAdmin):
    readonly_fields = ('id',)
    list_display = ('owner_username', 'method', 'value', 'is_active',)
    ordering = ('owner', 'method', 'value', 'is_active')

    def owner_username(self, instance):
        return instance.owner.username
    owner_username.short_description = _('Owner')


@admin.register(models.RefreshRecreateEventDetailView)
class RefreshRecreateEventDetailViewAdmin(admin.ModelAdmin):
    # NOTE: This class relies on celery.

    change_list_template = 'admin/activity/eventtype/event_detail_change_list.html'
    list_display = ('performed_by', 'refresh_at',
                    'recreated_at', 'maintenance_status')
    ordering = list_display

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
            qs_method(activity=action, status=f'Error ({name}): {task.info}')
            self.message_user(
                request, f"Failed to {name} 'event_detail_view'", messages.ERROR)
        if task.state == 'RETRY':
            qs_method(activity=action, status=task.state)
            self.message_user(
                request, f"Retry again to {name} 'event_detail_view'",  messages.WARNING)

        return HttpResponseRedirect("../")

    def refresh_view(self, request):
        task = refresh_event_details_view.apply_async(args=('Admin',))
        status = dict(self.model.STATUS_MESSAGE).get('REFRESH')
        qs_method = self.model.objects.refresh
        name = 'refresh'
        return self.manage_task_status(request=request,
                                       task=task,
                                       status=status,
                                       qs_method=qs_method,
                                       name=name)

    def recreate_view(self, request):
        task = recreate_event_details_view.delay()
        status = dict(self.model.STATUS_MESSAGE).get('SUCCESS')
        qs_method = self.model.objects.recreate
        name = 'recreate'
        return self.manage_task_status(request=request,
                                       task=task,
                                       status=status,
                                       qs_method=qs_method,
                                       name=name)


@AdminFeatureFlag(models.PatrolType, flag='PATROL_ENABLED')
@admin.register(models.PatrolType)
class PatrolTypeAdmin(admin.ModelAdmin):
    form = PatrolTypeForm
    readonly_fields = ('id',)
    list_display = ('display', 'value', 'ordernum', '_icon_display', 'is_active')
    search_fields = ('display', 'value')
    list_editable = ('ordernum', 'is_active',)

    def _icon_display(self, obj):
        url = models.PatrolType.marker_icon(obj.icon_id)
        return mark_safe(
            f'<img src="{url}" style="height:2.5em; filter:opacity(0.8)" />')
    _icon_display.short_description = 'Icon'


class PatrolState(Enum):
    overdue = 'start_overdue'
    ready = 'ready_to_start'
    scheduled = 'scheduled'
    active = 'active'
    done = models.PC_DONE
    cancelled = models.PC_CANCELLED


class PatrolStatusFilter(SimpleListFilter):
    title = 'Patrol status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            (PatrolState.overdue.value, 'Start Overdue'),
            (PatrolState.ready.value, 'Ready to Start'),
            (PatrolState.scheduled.value, 'Scheduled'),
            (PatrolState.active.value, 'Active'),
            (PatrolState.done.value, 'Done'),
            (PatrolState.cancelled.value, 'Cancelled'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(status=value)

        return queryset


@AdminFeatureFlag(models.Patrol, flag='PATROL_ENABLED')
@admin.register(models.Patrol)
class PatrolAdmin(OSMGeoExtendedAdmin):

    form = PatrolForm
    readonly_fields = ('id', 'serial_number')

    list_display = ('serial_number', 'title', 'patrol_type', 'tracked_subject_name', 'status',
                    'scheduled_start_date', 'actual_start_date', 'start_location', 'scheduled_end_date',
                    'actual_end_date', 'end_location')
    # fields = ('serial_number', 'title', 'patrol_type')
    fields = ('serial_number', 'title', 'patrol_type', 'tracked_subject', 'patrol_status', 'priority', 'scheduled_start_date',
              'actual_start_date', 'start_location', 'scheduled_end_date', 'actual_end_date', 'end_location')
    list_filter = ('patrol_segment__patrol_type__display',  PatrolStatusFilter)  # todo: filter by status
    list_display_links = ('serial_number', 'title')
    search_fields = ('title', 'patrol_segment__patrol_type__display')  # todo: filter tracked subject name

    ordering = ('serial_number', )
    actions = ('delete_patrol', )

    map_width = 600
    map_height = 300

    def get_queryset(self, request):
        queryset = super(PatrolAdmin, self).get_queryset(request)
        patrol_sgment = models.PatrolSegment.objects.filter(patrol_id=OuterRef('id'),
                                                            leader_content_type=F('leader_content_type'))
        subject = models.Subject.objects.filter(id=OuterRef('leader_id'))
        community = models.Community.objects.filter(id=OuterRef('leader_id'))
        user = get_user_model().objects.filter(id=OuterRef('leader_id'))

        set_time = datetime.datetime.now(tz=pytz.utc) - datetime.timedelta(minutes=30)
        end_day = set_time.replace(hour=23, minute=59, second=59, microsecond=999999)

        overdue = Q(patrol_segment__scheduled_start=F('patrol_segment__scheduled_start'), state=models.PC_OPEN) & \
                  Q(patrol_segment__time_range__startswith__isnull=True) & \
                  Q(patrol_segment__scheduled_start__lt=set_time)

        readyto = Q(patrol_segment__scheduled_start=F('patrol_segment__scheduled_start'), state=models.PC_OPEN) & \
                  Q(patrol_segment__time_range__startswith__isnull=True) & \
                  Q(patrol_segment__scheduled_start__range=(set_time,  end_day))

        scheduled = Q(patrol_segment__scheduled_start=F('patrol_segment__scheduled_start'), state=models.PC_OPEN) &\
                    Q(patrol_segment__time_range__startswith__isnull=True) & \
                    Q(patrol_segment__scheduled_start__gt=end_day)

        queryset = queryset.annotate(patrol_type=Subquery(patrol_sgment.values('patrol_type__display')[:1]),
                                     tracked_subject=Subquery(patrol_sgment.annotate(
                                         leader_name=Subquery(subject.values('name'))).values('leader_name')[:1]),
                                     tracked_user=Subquery(patrol_sgment.annotate(
                                         leader_name=Subquery(user.values('username'))).values('leader_name')[:1]),
                                     tracked_community=Subquery(patrol_sgment.annotate(
                                         leader_name=Subquery(community.values('name'))).values('leader_name')[:1]),
                                     scheduled_start=Subquery(patrol_sgment.values('scheduled_start')[:1]),
                                     scheduled_end=Subquery(patrol_sgment.values('scheduled_end')[:1]),
                                     start_time=Subquery(patrol_sgment.values('time_range__startswith')[:1]),
                                     end_time=Subquery(patrol_sgment.values('time_range__endswith')[:1]),
                                     start_location=Subquery(patrol_sgment.values('start_location')[:1]),
                                     end_location=Subquery(patrol_sgment.values('end_location')[:1]),
                                     status=Case(When(overdue, then=Value(PatrolState.overdue.value)),
                                                 When(readyto, then=Value(PatrolState.ready.value)),
                                                 When(scheduled, then=Value(PatrolState.scheduled.value)),
                                                 When(state=models.PC_OPEN, then=Value(PatrolState.active.value)),
                                                 default=F('state'), output_field=CharField()))
        return queryset

    def patrol_type(self, o):
        return o.patrol_type

    def tracked_subject_name(self, o):
        return o.tracked_subject

    def status(self, o):
        return ' '.join(o.status.split('_')).title()

    def scheduled_start_date(self, o):
        return o.scheduled_start
    scheduled_start_date.short_description = 'scheduled start date %s' % TIMEZONE_USED

    def scheduled_end_date(self, o):
        return o.scheduled_end
    scheduled_end_date.short_description = 'scheduled end date %s' % TIMEZONE_USED

    def actual_start_date(self, o):
        return o.start_time
    actual_start_date.short_description = 'actual start date %s' % TIMEZONE_USED

    def actual_end_date(self, o):
        return o.end_time
    actual_end_date.short_description = 'actual End Date %s' % TIMEZONE_USED

    def start_location(self, o):
        return f'{o.start_location.x:0.4} / {o.start_location.y:0.4}' if o.start_location else None
    start_location.short_description = 'start Location (Lon/Lat)'

    def end_location(self, o):
        return f'{o.end_location.x:0.4} / {o.end_location.y:0.4}' if o.end_location else None
    end_location.short_description = 'end location (lon/lat)'

    def has_add_permission(self, request):
        return False

    # def has_delete_permission(self, request, obj=None):
    #     return False

    def get_form(self, request, obj=None, change=False, **kwargs):
        """
        :param request:
        :param obj:
        :param change:
        :param kwargs:
        :return: form
        """
        form = super(PatrolAdmin, self).get_form(request, obj, change, **kwargs)
        if change:
            db_field = models.PatrolSegment._meta.get_field

            form.base_fields['patrol_type'].initial = obj.patrol_type
            form.base_fields['tracked_subject'].initial = obj.tracked_subject or obj.tracked_user or obj.tracked_community
            form.base_fields['patrol_status'].initial = obj.status
            form.base_fields['patrol_status'].disabled = True

            form.base_fields['scheduled_start_date'].initial = obj.scheduled_start
            form.base_fields['scheduled_end_date'].initial = obj.scheduled_end

            form.base_fields['actual_start_date'].initial = obj.start_time
            form.base_fields['actual_end_date'].initial = obj.end_time

            form.base_fields['end_location'].widget = self.get_map_widget(db_field('end_location'))()
            form.base_fields['end_location'].widget.attrs['map_srid'] = 4326
            form.base_fields['end_location'].initial = obj.end_location
            #
            form.base_fields['start_location'].widget = self.get_map_widget(db_field('start_location'))()
            form.base_fields['start_location'].widget.attrs['map_srid'] = 4326
            form.base_fields['start_location'].initial = obj.start_location

        return form

    @staticmethod
    def search_tracked_subject(search_term):
        q_object = Q(models.Subject.objects.filter(name__icontains=search_term)) | \
                   Q(get_user_model().objects.filter(username__icontains=search_term)) | \
                   Q(models.Community.objects.filter(name__icontains=search_term))

        return [i.values_list('id', flat=True)[0] for i in q_object.children if i]

    def get_search_results(self, request, queryset, search_term):
        qs = queryset
        queryset, use_distinct = super(PatrolAdmin, self).get_search_results(request, queryset, search_term)

        queryset |= qs.filter(patrol_segment__leader_id__in=self.search_tracked_subject(search_term))
        return queryset, use_distinct
