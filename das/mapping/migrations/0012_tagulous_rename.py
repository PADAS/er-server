from django.db import migrations
from django.db import connection


def forwards_fix_tagulous(apps, schema_editor):
    tagulous_table_name = 'mapping__tagulous_spatialfeaturetype_tags'
    model_name = 'SpatialFeatureTypeTag'
    if tagulous_table_name in connection.introspection.table_names():
        tag_model = apps.get_model('mapping', model_name)
        schema_editor.alter_db_table(
            tag_model,
            tagulous_table_name,
            tag_model._meta.db_table,
        )
        #now fix through m2m through fields
        tag_m2m_model = tag_model.spatialfeaturetype_set.through
        params = {
            'table': schema_editor.quote_name(tag_m2m_model._meta.db_table),
            'old_column': schema_editor.quote_name('_tagulous_spatialfeaturetype_tags_id'),
            'new_column': schema_editor.quote_name('spatialfeaturetypetag_id')}
        schema_editor.execute(schema_editor.sql_rename_column % params)



class Migration(migrations.Migration):

    dependencies = [
        ('mapping', '0011_spatial'),
    ]
    # 175,'mapping','_tagulous_spatialfeaturetype_tags' (django_content_type)
    # sql table rename mapping__tagulous_spatialfeaturetype_tags to mapping_spatialfeaturetypetag
    # fix intermediate table mapping_spatialfeaturetype_tags, field _tagulous_spatialfeaturetype_tags_id to spatialfeaturetypetag_id
    operations = [
        migrations.RunPython(forwards_fix_tagulous),

    ]
