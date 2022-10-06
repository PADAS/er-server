import datetime
import logging
from abc import ABC
from enum import Enum

from celery_once import AlreadyQueued
from psycopg2.extras import DateTimeTZRange

from django.contrib import messages
from django.contrib.admin import FieldListFilter, SimpleListFilter
from django.contrib.auth import get_permission_codename, get_user_model
from django.contrib.gis import admin
from django.db.models import (Case, CharField, F, OuterRef, Q, Subquery, Value,
                              When)
from django.db.utils import DataError
from django.forms.fields import JSONField
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

import activity.models as models
from activity.forms import (AlertRuleForm, EventForm, EventGeometryForm,
                            EventProviderForm, EventTypeForm, PatrolForm,
                            PatrolSegmentForm, PatrolSegmentStackedInline,
                            PatrolTypeForm, PrettyReadOnlyJSONWidget,
                            chained_tracked_by)
from activity.tasks import (recreate_event_details_view,
                            refresh_event_details_view)
from core.admin import InlineExtraDynamicMixin
from core.common import TIMEZONE_USED, AdminFeatureFlag
from core.openlayers import OSMGeoExtendedAdmin, PropsOSMGeoAdminMixin

logger = logging.getLogger(__name__)


class EventRelationshipInline(admin.TabularInline):
    model = models.EventRelationship
    fk_name = 'from_event'


class EventDetailsInline(admin.TabularInline):
    model = models.EventDetails


class EventGeometryInline(PropsOSMGeoAdminMixin, admin.StackedInline):
    model = models.EventGeometry
    max_num = 1
    can_delete = True
    verbose_name = _("Event Geometry")
    verbose_name_plural = _("Event Geometries")
    map_template = 'admin/openlayer/ol_geometry.html'
    form = EventGeometryForm

    def __init__(self, parent_model, admin_site):
        self.admin_site = admin_site
        self.parent_model = parent_model
        self.opts = self.model._meta
        self.has_registered_model = admin_site.is_registered(self.model)


@admin.register(models.Event)
class EventAdmin(OSMGeoExtendedAdmin):
    form = EventForm
    list_display = (
        "serial_number",
        "_created_at",
        "_event_time",
        "_updated_at",
        "event_type",
        "title",
        "_latitude",
        "_longitude",
    )
    ordering = (
        "serial_number",
    )
    sortable_by = (
        "serial_number",
        "_created_at",
        "_event_time",
        "_updated_at",
        "event_type",
        "title",
    )
    readonly_fields = ('id', 'serial_number', 'created_at', 'updated_at')
    search_fields = ('title', 'serial_number')
    list_filter = ('state', 'event_type', )
    actions = ('resolve_event',)
    inlines = (
        EventDetailsInline,
    )

    fieldsets = (
        (None, {
            'fields': ('serial_number', 'title', 'event_type', 'event_time', 'end_time',)
        }),
        ('Advanced', {
            'classes': ('wide', 'collapse',),
            'fields': ('state', 'priority', 'location', 'id', 'created_at', 'updated_at',)
        }),
    )

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        self.inlines = (EventGeometryInline, *self.inlines)

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
    ordering = ('display', 'value', 'ordernum', 'category',
                'default_priority', 'default_state')
    list_filter = ('category',)
    list_display = ('display', 'value', 'ordernum',
                    'category', 'is_collection', '_default_priority_display', '_icon_display', 'default_state', 'is_active')
    list_editable = ('ordernum', 'default_state',)
    list_display_links = ('display',)
    search_fields = ('display', 'value',)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "display",
                    "value",
                    "category",
                    "is_collection",
                    "icon",
                    "ordernum",
                    "auto_eventtype_resolve",
                    "geometry_type"
                )
            },
        ),
        ("Default Values", {
         "fields": ("default_priority", "default_state", "is_active")}),
        (
            "Schema & Form Definition",
            {
                "classes": ("wide",),
                "fields": ("schema",),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ["geometry_type"]
        return []

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

    def save_form(self, request, form, change):
        auto_resolve = form.cleaned_data.get('auto_resolve')
        resolve_time = form.cleaned_data.get('resolve_time')
        new_object = super().save_form(request, form, change)

        if auto_resolve is not None:
            new_object.auto_resolve = auto_resolve
            new_object.resolve_time = resolve_time
        return new_object


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
    list_display = ('performed_by', 'task_mode', 'started_at',
                    'ended_at', 'maintenance_status')
    fields = ('id', 'performed_by', 'task_mode',
              'started_at', 'ended_at', 'error_details')
    ordering = ('-started_at', )

    formfield_overrides = {
        JSONField: {'widget': PrettyReadOnlyJSONWidget}
    }

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

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if not f.name == 'error_details']

    def manage_task_status(self, request, task, task_mode,  qs_method, name):
        action = 'Admin'
        obj = qs_method(activity=action, task_mode=task_mode)
        filter_func = self.model.objects.filter

        while not task.ready():
            logger.info(f'State={task.state}, info={task.info}')

        if task.state == 'PENDING' or task.state == 'STARTED':
            filter_func(id=obj.id).update_status(status=self.model.RUNNING)
        if task.state == 'SUCCESS':
            success = self.model.SUCCESS_WARNING if task.result else self.model.SUCCESS
            filter_func(id=obj.id).update_status_and_ended_at(
                status=success, error_details=task.result)
            self.message_user(
                request, f"Successfully {name} 'event_detail_view'")
        if task.state == 'FAILURE':
            error_details = [
                {f'action to {name}': f'failed with exception {task.info}'}]
            filter_func(id=obj.id).update_status_and_ended_at(
                status=self.model.FAILED, error_details=error_details)
            self.message_user(
                request, f"Failed to {name} 'event_detail_view'", messages.ERROR)
        if task.state == 'RETRY':
            filter_func(id=obj.id).update_status(status=task.state)
            self.message_user(
                request, f"Retry again to {name} 'event_detail_view'",  messages.WARNING)

        return HttpResponseRedirect("../")

    def refresh_view(self, request):
        try:
            task = refresh_event_details_view.apply_async(args=('Admin',))
        except AlreadyQueued:
            self.message_user(
                request, f"Task to refresh event_detail view is already queued",  messages.WARNING)
            return HttpResponseRedirect("../")

        task_mode = self.model.REFRESH
        qs_method = self.model.objects.refresh
        name = 'refresh'
        return self.manage_task_status(request=request,
                                       task=task,
                                       task_mode=task_mode,
                                       qs_method=qs_method,
                                       name=name)

    def recreate_view(self, request):
        try:
            task = recreate_event_details_view.apply_async()
        except AlreadyQueued:
            self.message_user(
                request, f"Task to recreate event_detail view is already queued",  messages.WARNING)
            return HttpResponseRedirect("../")

        # status = dict(self.model.STATUS_MESSAGE).get('SUCCESS')
        task_mode = self.model.RECREATE
        qs_method = self.model.objects.recreate
        name = 'recreate'
        return self.manage_task_status(request=request,
                                       task=task,
                                       task_mode=task_mode,
                                       qs_method=qs_method,
                                       name=name)


@AdminFeatureFlag(models.PatrolType, flag='PATROL_ENABLED')
@admin.register(models.PatrolType)
class PatrolTypeAdmin(admin.ModelAdmin):
    form = PatrolTypeForm
    readonly_fields = ('id',)
    list_display = ('display', 'value', 'ordernum',
                    '_icon_display', 'is_active')
    search_fields = ('display', 'value')
    list_editable = ('ordernum', 'is_active',)

    def _icon_display(self, obj):
        url = models.PatrolType.marker_icon(obj.icon_id)
        return mark_safe(
            f'<img src="{url}" style="height:2.5em; filter:opacity(0.8)" />')
    _icon_display.short_description = 'Icon'


class PatrolPermissionMixin:
    patrol_opts = models.Patrol._meta

    def has_add_permission(self, request, obj=None):
        opts = self.patrol_opts
        codename = get_permission_codename('add', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_change_permission(self, request, obj=None):
        opts = self.patrol_opts
        codename = get_permission_codename('change', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_delete_permission(self, request, obj=None):
        opts = self.patrol_opts
        codename = get_permission_codename('delete', opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    def has_view_permission(self, request, obj=None):
        opts = self.patrol_opts
        codename_view = get_permission_codename('view', opts)
        codename_change = get_permission_codename('change', opts)
        return (
            request.user.has_perm(f"{opts.app_label}.{codename_view}") or
            request.user.has_perm(f"{opts.app_label}.{codename_change}"))


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
        # Let the value be an tuple of status strings to be used in an in-clause.
        return (
            (PatrolState.overdue.value, 'Start Overdue'),
            ('$'.join((PatrolState.ready.value, PatrolState.overdue.value)),
             'Ready to Start'),
            ('$'.join((PatrolState.ready.value, PatrolState.overdue.value,
                       PatrolState.scheduled.value)), 'Scheduled'),
            (PatrolState.active.value, 'Active'),
            (PatrolState.done.value, 'Done'),
            (PatrolState.cancelled.value, 'Cancelled'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(status__in=value.split('$'))

        return queryset


def update_filter_name(title):
    class Wrapper(FieldListFilter, ABC):
        def __new__(cls, *args, **kwargs):
            instance = FieldListFilter.create(*args, **kwargs)
            instance.title = title
            return instance
    return Wrapper


class PatrolSegmentInline(PatrolPermissionMixin, PatrolSegmentStackedInline):
    max_num = 1
    can_delete = False
    fields = ('id', 'patrol_type', 'tracked_subject', 'scheduled_start',
              'start_time', 'start_location', 'scheduled_end', 'end_time', 'end_location')
    form = PatrolSegmentForm
    map_width = 600
    map_height = 300
    model = models.PatrolSegment

    def get_formset(self, request, obj=None, **kwargs):
        setattr(self.model, 'user', request.user)
        return super(PatrolSegmentInline, self).get_formset(request, obj, **kwargs)


@AdminFeatureFlag(models.Patrol, flag='PATROL_ENABLED')
@admin.register(models.Patrol)
class PatrolAdmin(PatrolPermissionMixin, OSMGeoExtendedAdmin):
    inlines = [PatrolSegmentInline]
    form = PatrolForm
    readonly_fields = ('id', 'serial_number')

    list_display = ('serial_number', 'title', 'patrol_type', 'tracked_subject_name', 'status',
                    'scheduled_start_date', 'actual_start_date', 'start_location', 'scheduled_end_date',
                    'actual_end_date', 'end_location')

    fields = ('serial_number', 'title', 'priority', 'patrol_status')

    list_filter = (PatrolStatusFilter,  ('patrol_segment__patrol_type__display',
                                         update_filter_name('Patrol Type')))
    list_display_links = ('serial_number', 'title')
    search_fields = ('title', 'patrol_segment__patrol_type__display')

    ordering = ('serial_number', )

    def _allowed_tracked_subject(self, user):
        tracked_subjects = chained_tracked_by(user)
        subjects = []
        users = []
        for v in dict(tracked_subjects).values():
            if isinstance(v, models.Subject):
                subjects.append(v.id)
            if isinstance(v, get_user_model()):
                users.append(v.id)
        return subjects, users

    def get_queryset(self, request):
        queryset = super(PatrolAdmin, self).get_queryset(request)
        patrol_sgment = models.PatrolSegment.objects.filter(
            patrol_id=OuterRef('id')).order_by('created_at')
        subject = models.Subject.objects.filter(id=OuterRef('leader_id'))
        user = get_user_model().objects.filter(id=OuterRef('leader_id'))
        subjects, users = self._allowed_tracked_subject(request.user)

        # Anchor both boundaries on the present time, to handle cases where set_time turns out to be 'yesterday'.
        present_time = timezone.localtime()
        set_time = present_time - datetime.timedelta(minutes=30)
        end_day = (present_time + datetime.timedelta(days=1)
                   ).replace(hour=0, minute=0, second=0, microsecond=0)

        overdue = Q(patrol_segment__scheduled_start=F('patrol_segment__scheduled_start'), state=models.PC_OPEN) & \
            Q(patrol_segment__time_range__startswith__isnull=True) & \
            Q(patrol_segment__scheduled_start__lt=set_time)

        readyto = Q(state=models.PC_OPEN) & \
            Q(patrol_segment__time_range__startswith__range=(present_time, end_day)) | \
            Q(patrol_segment__scheduled_start__range=(set_time,  end_day))

        scheduled = Q(state=models.PC_OPEN) &\
            (Q(patrol_segment__time_range__startswith__gt=end_day) |
             Q(patrol_segment__scheduled_start__gt=end_day))

        queryset = queryset.annotate(patrol_type=Subquery(patrol_sgment.values('patrol_type__display')[:1]),
                                     tracked_subject=Subquery(patrol_sgment.annotate(
                                         leader_name=Subquery(subject.filter(Q(id__in=subjects)).values('name'))).values('leader_name')[:1]),
                                     tracked_user=Subquery(patrol_sgment.annotate(
                                         leader_name=Subquery(user.filter(Q(id__in=users)).values('username'))).values('leader_name')[:1]),
                                     scheduled_start=Subquery(
                                         patrol_sgment.values('scheduled_start')[:1]),
                                     scheduled_end=Subquery(
                                         patrol_sgment.values('scheduled_end')[:1]),
                                     start_time=Subquery(patrol_sgment.values(
                                         'time_range__startswith')[:1]),
                                     end_time=Subquery(patrol_sgment.values(
                                         'time_range__endswith')[:1]),
                                     start_location=Subquery(
                                         patrol_sgment.values('start_location')[:1]),
                                     end_location=Subquery(
                                         patrol_sgment.values('end_location')[:1]),
                                     status=Case(When(overdue, then=Value(PatrolState.overdue.value)),
                                                 When(readyto, then=Value(
                                                     PatrolState.ready.value)),
                                                 When(scheduled, then=Value(
                                                     PatrolState.scheduled.value)),
                                                 When(state=models.PC_OPEN, then=Value(
                                                     PatrolState.active.value)),
                                                 default=F('state'), output_field=CharField()))
        return queryset

    def patrol_type(self, o):
        return o.patrol_type

    def tracked_subject_name(self, o):
        value = o.tracked_subject or o.tracked_user
        return value if value else None

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

    def has_add_permission(self, request, obj=None):
        return False

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super(PatrolAdmin, self).get_form(
            request, obj, change, **kwargs)
        if change:
            form.base_fields['patrol_status'].initial = ' '.join(
                obj.status.split('_')).title()
            form.base_fields['patrol_status'].disabled = True
        return form

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except DataError:
            self.message_user(request,
                              _("Actual start date must be earlier or equal to Actual end date"),
                              level=messages.ERROR)
            return HttpResponseRedirect(request.get_full_path())

    @staticmethod
    def search_tracked_subject(search_term):
        q_object = Q(models.Subject.objects.filter(name__icontains=search_term)) | \
            Q(get_user_model().objects.filter(username__icontains=search_term))

        return [i.values_list('id', flat=True)[0] for i in q_object.children if i]

    def get_search_results(self, request, queryset, search_term):
        qs = queryset
        queryset, use_distinct = super(PatrolAdmin, self).get_search_results(
            request, queryset, search_term)

        queryset |= qs.filter(
            patrol_segment__leader_id__in=self.search_tracked_subject(search_term))
        return queryset, use_distinct

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        start_time = formset.cleaned_data[0].get('start_time')
        end_time = formset.cleaned_data[0].get('end_time')
        tracked_subject = formset.cleaned_data[0].get('tracked_subject')

        for instance in instances:
            instance.patrol = formset.instance
            if start_time and end_time:
                instance.time_range = DateTimeTZRange(
                    lower=start_time, upper=end_time)
            elif start_time:
                instance.time_range = DateTimeTZRange(lower=start_time)
            elif end_time:
                instance.time_range = DateTimeTZRange(upper=end_time)
            if tracked_subject:
                instance.leader = tracked_subject
            instance.save()


@AdminFeatureFlag(models.PatrolConfiguration, flag='PATROL_ENABLED')
@admin.register(models.PatrolConfiguration)
class PatrolConfiguration(admin.ModelAdmin):
    list_display = ('name',)
    filter_horizontal = ('subject_groups',)

    def has_add_permission(self, request):
        if self.model.objects.count():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
