from django.contrib import admin
import activity.models as models


class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event_type', 'name', 'location', 'attributes',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [
        EventAttachmentInline,
    ]


    # list_display = ['id', 'plugin_class', 'plugin_name', 'created_at', 'updated_at', 'configuration']

@admin.register(models.EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    pass



