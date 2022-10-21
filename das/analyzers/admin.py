import analyzers.models as models
from analyzers.forms import (EnvironmentalAnalyzerAdminForm,
                             FeatureProximityAnalyzerForm,
                             GeofenceSubjectAnalyzerForm,
                             GlobalForestWatchSubscriptionForm,
                             ImmobilityAnalyzerForm,
                             LowSpeedPercentileSubjectAnalyzerForm,
                             LowSpeedWilcoxSubjectAnalyzerForm,
                             SubjectProximityAnalyzerForm)
from core.openlayers import OSMGeoExtendedAdmin
from django.contrib import admin


@admin.register(models.ImmobilityAnalyzerConfig)
class ImmobilityAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    ordering = ('name', 'subject_group')
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)
    form = ImmobilityAnalyzerForm

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
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
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
    ordering = ('name', 'subject_group')
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name
    subject_group_name.admin_order_field = 'subject_group'

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', 'subject_group', 'is_active'),
        }
        ),
        ('Environmental Analysis Parameters', {
            'classes': ('wide',),
            'fields': ('threshold_value', 'scale_meters', 'GEE_img_name', 'GEE_img_band_name', 'short_description',)
        }),
        ('Earth Engine Access', {
            'description': EARTH_ENGINE_KEY_DESCRIPTION,
            'classes': ('wide', 'collapse',),
            'fields': ('earth_engine_json_key',)
        }),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
        })
    )

    form = EnvironmentalAnalyzerAdminForm


@admin.register(models.FeatureProximityAnalyzerConfig)
class FeatureProximityAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    ordering = ('name', 'subject_group')

    search_fields = ('subject_group__name',)
    readonly_fields = ('id',)
    form = FeatureProximityAnalyzerForm

    def subject_group_name(self, o):
        return o.subject_group.name
    subject_group_name.admin_order_field = 'subject_group'

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
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
        })
    )


@admin.register(models.SubjectProximityAnalyzerConfig)
class SubjectProximityAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_1_name', 'subject_group_2_name')
    ordering = ('name', 'subject_group', 'second_subject_group')

    search_fields = ('subject_group__name',
                     'second_subject_group__name', 'name',)
    readonly_fields = ('id',)
    form = SubjectProximityAnalyzerForm

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'second_subject_group', 'threshold_dist_meters',
                        'proximity_time', 'is_active',))
        }),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'analysis_search_time_hours', 'quiet_period', 'notes',)
        })
    )

    def subject_group_1_name(self, o):
        return o.subject_group.name
    subject_group_1_name.admin_order_field = 'subject_group'

    def subject_group_2_name(self, o):
        return o.second_subject_group.name
    subject_group_2_name.admin_order_field = 'second_subject_group'


@admin.register(models.GeofenceAnalyzerConfig)
class GeofenceSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    ordering = ('name', 'subject_group')
    search_fields = ('subject_group__name',)
    readonly_fields = ('id',)
    form = GeofenceSubjectAnalyzerForm

    def subject_group_name(self, o):
        return o.subject_group.name
    subject_group_name.admin_order_field = 'subject_group'

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
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
        })
    )


@admin.register(models.LowSpeedWilcoxAnalyzerConfig)
class LowSpeedWilcoxSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    ordering = ('name', 'subject_group')
    readonly_fields = ('id',)
    search_fields = ('subject_group__name',)
    form = LowSpeedWilcoxSubjectAnalyzerForm

    def subject_group_name(self, o):
        return o.subject_group.name
    subject_group_name.admin_order_field = 'subject_group'

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active', 'low_speed_probability_cutoff',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
        })
    )


@admin.register(models.LowSpeedPercentileAnalyzerConfig)
class LowSpeedPercentileSubjectAnalyzerAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject_group_name',)
    ordering = ('name', 'subject_group')
    readonly_fields = ('id',)
    form = LowSpeedPercentileSubjectAnalyzerForm

    search_fields = ('subject_group__name',)

    def subject_group_name(self, o):
        return o.subject_group.name
    subject_group_name.admin_order_field = 'subject_group'

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('name', 'subject_group', 'is_active', 'low_threshold_percentile', 'default_low_speed_value',))
        }
        ),
        ('Advanced Analyzer Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'search_time_hours', 'quiet_period', 'notes',)
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
    readonly_fields = ('subscription_id', 'geostore_id',
                       'last_check_time', 'last_check_status')

    list_display = ('name', 'subscription_id',
                    'last_check_time', 'last_check_status')
    ordering = list_display

    gis_geometry_field_name = 'subscription_geometry'

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', 'last_check_time', 'last_check_status')
        }),
        ('Global Forest Watch API Properties', {
            'classes': ('wide',),
            'fields': ('alert_types', 'subscription_id', 'geostore_id',)
        }),
        ('Advanced Attributes', {
            'classes': ('wide', 'collapse'),
            'fields': ('id', 'additional', 'glad_confirmed_backfill_days')
        }),
        ('Global Forest Watch Alerts Confidence Level', {
            'fields': ('Deforestation_confidence', 'Fire_confidence')
        }),
        ('Geographical Area', {
            'fields': ('subscription_geometry',)
        })
    )
