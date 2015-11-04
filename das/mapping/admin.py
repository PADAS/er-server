from django.contrib.gis import admin
import mapping.models as models

# Register your models here.


@admin.register(models.Map)
class MapAdmin(admin.OSMGeoAdmin):
    pass


@admin.register(models.TileLayer)
class TileLayerAdmin(admin.ModelAdmin):
    pass

