from django.contrib import admin
import activity.models as models


class EventAttachmentInline(admin.StackedInline):
    model=models.EventAttachment

@admin.register(models.Event)
class EventAdmin(admin.ModelAdmin):
    inlines = [
        EventAttachmentInline,
    ]

@admin.register(models.EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    pass



