from django.contrib.gis import admin
import activity.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.forms import Textarea


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
    list_filter = ('event_type',)
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


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventRelatedSubject)
class EventRelatedSubject(admin.ModelAdmin):
    ordering = ('event__id', 'subject')


@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):
    ordering = ('category', 'ordernum', 'display',)
    list_filter = ('category',)
    list_display = ('display', 'value', 'ordernum',
                    'category', 'is_collection')
    list_editable = ('ordernum',)
    fieldsets = (
        (None, {
            'fields': ('display', 'value', 'is_collection', 'ordernum', 'category',)
        }
        ),
        ('Schema & Definition',
         {
             'fields': ('schema', 'icon', 'default_priority'),
         })
    )


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
    list_display = ('display', 'owner', 'event_type', 'is_active',)
    readonly_fields = ('external_event_type', 'id',)

    fieldsets = (
        (None, {
            'fields': ('display', 'event_type', 'is_active',)
        }),
        ('Advanced', {
            'fields': ('owner', 'external_event_type', 'id'),
            'classes': ('wide', 'collapse',)
        })
    )


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
