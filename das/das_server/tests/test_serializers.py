from das_server.serializers import VersionSerializer


class TestVersionSerializer:
    def test_serialized_version(self):
        version = dict(show_track_days=16, default_event_filter_from_days=-1, default_patrol_filter_from_days=-1)

        serialized_version = VersionSerializer(version).data

        assert serialized_version["show_track_days"] == version["show_track_days"]
        assert serialized_version["default_event_filter_from_days"] == version["default_event_filter_from_days"]
        assert serialized_version["default_patrol_filter_from_days"] == version["default_patrol_filter_from_days"]
