# Generated by Django 2.0.13 on 2020-01-17 23:56

from django.db import migrations

TILE_TYPE_CHOICES = [
    {
        "value": "google_map",
        "display": "Google Map (Legacy)",
    },
    {
        "value": "tile_server",
        "display": "Tile Server",
    },
    {

        "value": "mapbox_style",
        "display": "Mapbox Style",

    },
    {
        "value": "mapbox_tiles",
        "display": "Mapbox Tiles (Legacy)",

    },
]

maps_to_delete = ["5b480df1-dea2-4536-9a3f-03ce5b825abe",
                  "41814d8e-5811-410c-a195-a4ebee9dbf5a"]

primary_keys = {
    "Google_Satellite": "d57ea783-dbf6-4e2f-aa35-89d24b9ed30a",
    "Mapbox_Satellite": "8b297282-164d-4604-a144-ceedefef605a"
}

Mapbox_satellite_conf = {
    "url": "https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.png?access_token=pk.eyJ1IjoidmpvZWxtIiwiYSI6ImNpZ3RzNXdmeDA4cm90N2tuZzhsd3duZm0ifQ.YcHUz9BmCk2oVOsL48VgVQ",
    "type": "tile_server",
    "title": "Mapbox Satellite Map",
}

Google_satellite_conf = {
    "url": "https://mt.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "type": "tile_server",
    "title": "Google Satellite",
    "icon_url": "https://maps.google.com/mapfiles/ms/icons/red-dot.png",
}


def create_tile_type_choice(app_registry, db_alias, value, display):
    Choice = app_registry.get_model('choices', 'Choice')
    model = "mapping.TileLayer"
    field = "service_type"
    choice, created = Choice.objects.using(db_alias).get_or_create(
        model=model,
        field=field,
        value=value,
        defaults=dict(display=display)
    )


def update_existing_tilelayer_conf(app_registry, schema_editor):
    # We get the model from the versioned app registry
    tile_layer = app_registry.get_model('mapping', 'TileLayer')
    db_alias = schema_editor.connection.alias
    required_args = (tile_layer, db_alias)

    # Add tile service choices
    for service in TILE_TYPE_CHOICES:
        create_tile_type_choice(app_registry, db_alias,
                                service['value'], service['display'])

    # Remove DAS-Terrain maps
    for das_terrain_pk in maps_to_delete:
        status, das_terrain_qs = check_object_exist(
            das_terrain_pk, *required_args)
        if status:
            das_terrain_qs.delete()

    # Update Google Satellite url
    google_sat_pk = primary_keys.get('Google_Satellite')
    google_layer, created = tile_layer.objects.using(db_alias).get_or_create(
        pk=google_sat_pk,
        defaults=dict(name=Google_satellite_conf['title'],
                      attributes=Google_satellite_conf))
    if not created:
        google_layer.attributes = Google_satellite_conf
        google_layer.save()

    # Update Mapbox Satellite Map to use conf
    mapbox_sat_pk = primary_keys.get('Mapbox_Satellite')
    mapbox_layer, created = tile_layer.objects.using(db_alias).get_or_create(
        pk=mapbox_sat_pk,
        defaults=dict(name=Mapbox_satellite_conf['title'],
                      attributes=Mapbox_satellite_conf))
    if not created:
        mapbox_layer.attributes = Mapbox_satellite_conf
        mapbox_layer.name = Mapbox_satellite_conf['title']
        mapbox_layer.save()


def check_object_exist(pk, model, db_alias):
    try:
        queryset = model.objects.using(db_alias).get(pk=pk)
    except model.DoesNotExist:
        return False, None
    return True, queryset


class Migration(migrations.Migration):
    dependencies = [
        ('mapping', '0022_mapping_features_v2'),
    ]

    operations = [
        migrations.RunPython(update_existing_tilelayer_conf,
                             reverse_code=migrations.RunPython.noop)
    ]
