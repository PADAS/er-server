from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.conf import settings
import analyzers.models as models

# if settings.DEBUG:
#
#     @admin.register(models.GeofenceAnalyzer)
#     class GeofenceAnalyzerAdmin(ModelAdmin):
#         pass
#
#     @admin.register(models.SubjectAnalyzer)
#     class SubjectAnalyzerAdmin(admin.ModelAdmin):
#         pass
#
#     @admin.register(models.ObservationAnnotator)
#     class ObservationAnnotatorAdmin(admin.ModelAdmin):
#         pass
#
#     @admin.register(models.ImmobilityAnalyzer)
#     class ImmobilityAnalyzerAdmin(admin.ModelAdmin):
#         list_display = ('id', 'name', 'get_subject_name',
#                         )
#
#         search_fields = ('subject__name',)
#
#         def get_subject_name(self, o):
#             return o.subject.name