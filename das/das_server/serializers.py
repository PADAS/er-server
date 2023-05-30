import rest_framework.serializers


class VersionSerializer(rest_framework.serializers.Serializer):
    version = rest_framework.serializers.CharField(read_only=True)
    show_track_days = rest_framework.serializers.IntegerField(read_only=True)
    event_matrix_enabled = rest_framework.serializers.BooleanField(read_only=True)
    event_search_enabled = rest_framework.serializers.BooleanField(read_only=True)
    export_kml_enabled = rest_framework.serializers.BooleanField(read_only=True)
    db_connection_count = rest_framework.serializers.IntegerField(read_only=True)
    eus_settings = rest_framework.serializers.DictField(read_only=True)

    show_stationary_subjects_on_map = rest_framework.serializers.BooleanField(read_only=True)

    daily_report_enabled = rest_framework.serializers.BooleanField(read_only=True)

    alerts_enabled = rest_framework.serializers.BooleanField(read_only=True)
    tableau_enabled = rest_framework.serializers.BooleanField(read_only=True)

    services = rest_framework.serializers.ListField(read_only=True)

    server_timezone_name = rest_framework.serializers.CharField(read_only=True)
    server_timezone = rest_framework.serializers.CharField(read_only=True)

    eula_enabled = rest_framework.serializers.BooleanField(read_only=True)
    patrol_enabled = rest_framework.serializers.BooleanField(read_only=True)
    messaging_enabled = rest_framework.serializers.BooleanField(read_only=True)
    site_name = rest_framework.serializers.CharField(read_only=True)
    last_migration_app = rest_framework.serializers.CharField(read_only=True)
    last_migration_name = rest_framework.serializers.CharField(read_only=True)
    track_length = rest_framework.serializers.IntegerField(read_only=True)
    default_event_filter_from_days = rest_framework.serializers.IntegerField(read_only=True)
    default_patrol_filter_from_days = rest_framework.serializers.IntegerField(read_only=True)
