from django.contrib import admin
import django.contrib.gis.admin as gis_admin

import analyzers.models as models
from analyzers.forms import EnvironmentalAnalyzerAdminForm, GlobalForestWatchSubscriptionForm
from core.openlayers import OSMGeoExtendedAdmin


# @admin.register(models.ObservationAnnotator)
# class ObservationAnnotatorAdmin(admin.ModelAdmin):

#     list_display = ('subject_name', 'max_speed', 'subject_subtype',)
#     list_editable = ('max_speed',)
#     search_fields = ('subject_name',)
#     list_filter = ('max_speed', 'subject__subject_subtype__display',
#                    'subject__subject_subtype__subject_type__display',)
#     ordering = ('subject__name', )
#     readonly_fields = ('id',)

#     def subject_name(self, o):
#         return o.subject.name

#     def subject_subtype(self, o):
#         return o.subject.subject_subtype.value


@admin.register(models.ImmobilityAnalyzerConfig)
class ImmobilityAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active'))
        }
        ),
        ('Speed Threshold Parameters', {
            'classes': ('wide',),
            'fields': ('threshold_radius', 'threshold_time', 'threshold_probability',)
        }),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'notes',)
        })
    )

google_earthengine_service_account_link = 'https://developers.google.com/earth-engine/service_account'
EARTH_ENGINE_KEY_DESCRIPTION = f'''
<p>
This analyzer requires access to Google's Earth Engine API using a service account private key.
</p>
<p>To learn how to get a service account key, visit
 <a target="_blank" href="{google_earthengine_service_account_link}">{google_earthengine_service_account_link}</a>.
<br/>
Once you have a service account, you can create a private key for it. Download the
private key and paste it's contents in this form (be sure to use the JSON format key).
'''


@admin.register(models.EnvironmentalSubjectAnalyzerConfig)
class EnvironmentalSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', 'subject_group', 'is_active'),
        }
        ),
        ('Environmental Analysis Parameters', {
            'classes': ('wide',),
            'fields': ('threshold_value', 'scale_meters', 'GEE_img_name', 'GEE_img_band_name', 'short_description',
                       'search_time_hours', 'notes',)
        }),
        ('Earth Engine Access', {
            'description': EARTH_ENGINE_KEY_DESCRIPTION,
            'classes': ('wide', 'collapse',),
            'fields': ('earth_engine_json_key',)
        }),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id',)
        })
    )

    form = EnvironmentalAnalyzerAdminForm


@admin.register(models.ProximityAnalyzerConfig)
class ProximitySubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)

    search_fields = ('subject_group__name',)
    readonly_fields = ('id',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'threshold_dist_meters',
                        'is_active',))
        }
        ),
        ('Spatial Features', {
            'classes': ('wide',),
            'fields': (('proximal_features',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'notes',)
        })
    )


@admin.register(models.GeofenceAnalyzerConfig)
class GeofenceSubjectAnalyzerAdmin(admin.ModelAdmin):

    list_display = ('name', 'subject_group_name',)
    search_fields = ('subject_group__name',)
    readonly_fields = ('id',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active',))
        }
        ),
        ('Spatial Features', {
            'classes': ('wide',),
            'fields': (('critical_geofence_group', 'warning_geofence_group', 'containment_regions',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'threshold_time', 'search_time_hours', 'notes',)
        })
    )


@admin.register(models.LowSpeedWilcoxAnalyzerConfig)
class LowSpeedWilcoxSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active', 'low_speed_probability_cutoff',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'notes',)
        })
    )


@admin.register(models.LowSpeedPercentileAnalyzerConfig)
class LowSpeedPercentileSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    readonly_fields = ('id',)

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active', 'low_threshold_percentile', 'default_low_speed_value',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'notes',)
        })
    )


@admin.register(models.SubjectSpeedProfile)
class SubjectSpeedProfileAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpeedDistro)
class SpeedDistroAdmin(admin.ModelAdmin):
    pass


@admin.register(models.GlobalForestWatchSubscription)
class GlobalForestWatchAdmin(OSMGeoExtendedAdmin):
    form = GlobalForestWatchSubscriptionForm
    readonly_fields = ('subscription_id', 'geostore_id',)

    list_display = ('name', 'subscription_id',)

    gis_geometry_field_name = 'subscription_geometry'

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', )
        }),
        ('Global Forest Watch API Properties', {
            'classes': ('wide',),
            'fields': ('alert_types', 'subscription_id', 'geostore_id',)
        }),
        ('Advanced Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'additional')
        }),
        ('Geographical Area', {
            'fields': ('subscription_geometry',)
        })
    )

