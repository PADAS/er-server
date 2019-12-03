from django.contrib import admin
import feature_flags.models as models


@admin.register(models.FeatureFlag)
class FeatureFlagsAdmin(admin.ModelAdmin):
    list_display = ('name', 'value',)
