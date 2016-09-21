from django.contrib.gis import admin
import activity.models as models
from django.contrib.staticfiles.templatetags.staticfiles import static

class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(admin.OSMGeoAdmin):
    openlayers_url = static('js/openlayers_2.13/OpenLayers.js')
    wms_layer = 'terrain,overlay'
    wms_url= 'http://tiles.maps.eox.at/wms/'

    list_display = ('created_at', 'event_type', 'message', 'location', 'attributes',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [
        EventAttachmentInline,
    ]


    # list_display = ['id', 'plugin_class', 'plugin_name', 'created_at', 'updated_at', 'configuration']


@admin.register(models.Community)
class CommunityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):
    ordering = ('ordernum', 'display',)
    list_display = ('display', 'ordernum',)
    fieldsets = (
        (None, {
            'fields': ('display', 'value', 'ordernum', 'schema',
                       )}
         ),
    )


@admin.register(models.EventClass)
class EventClassAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventFactor)
class EventFactorAdmin(admin.ModelAdmin):
    pass


@admin.register(models.EventClassFactor)
class EventClassFactorAdmin(admin.ModelAdmin):
    list_display = ('class_display', 'factor_display', 'priority')
    ordering = ('eventclass__ordernum', 'eventfactor__ordernum')

    def class_display(self, instance):
        return instance.eventclass.display

    def factor_display(self, instance):
        return instance.eventfactor.display