import pytest

from django.contrib.gis.geos import Point
from django.utils import timezone

from observations.models import Observation
from observations.serializers import ObservationSerializer


@pytest.mark.django_db
class TestObservationSerializer:
    @pytest.mark.parametrize("coordinates", [(0, 0), (-103.313486, 20.420935)])
    def test_serialized_observation(self, subject_source, coordinates):
        source = subject_source.source
        provider = subject_source.source.provider
        provider.transforms = [
            {"dest": "voltage", "label": "voltage",
                "units": "v", "source": "voltage"},
            {"dest": "altitude", "label": "altitude",
                "units": "feet", "source": "altitude"}
        ]
        provider.save()
        now = timezone.now()
        point = Point(coordinates)
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": {"voltage": 10, "altitude": 20},
        }
        representation = {
            "source_id": "af1402d7-ad60-41ec-a69f-44461cb32141",
            "source_transforms": [
                {
                    "dest": "speed",
                    "label": "speed",
                    "source": "speed",
                    "units": "km"
                }
            ],
            "additional": {
                "speed": 10
            },
            "location": point
        }
        observation = Observation.objects.create(**data)

        serialized_observation = ObservationSerializer(observation)
        serialized_observation_data = serialized_observation.data
        serialized_dict_representation = serialized_observation.dict_to_representation(
            representation, {"include_details": True})

        assert serialized_observation_data["id"] == str(observation.id)
        assert serialized_observation_data["location"] == {
            "latitude": float(coordinates[1]),
            "longitude": float(coordinates[0]),
        }
        assert serialized_observation_data["recorded_at"] == now.astimezone(
        ).isoformat()
        assert (
            serialized_observation_data["created_at"]
            == observation.created_at.astimezone().isoformat()
        )
        assert serialized_observation_data["source"] == str(source.id)
        assert serialized_dict_representation["source"] == representation.get(
            "source")
        assert serialized_dict_representation["device_status_properties"] == [
            {"value": 10, "label": "speed", "units": "km"}]
        assert serialized_dict_representation["observation_details"] == representation.get(
            "observation_details")
        assert serialized_dict_representation["location"] == {"longitude": representation.get(
            "location").get("longitude"), "latitude": representation.get("location").get("latitude")}
