import pytest
import json
from dateutil import parser as date_parser

from django.utils import timezone
from django.contrib.gis.geos import Point

from das.buoy.serializers import GearsSerializer
from observations.models import (
    Observation,
)
from utils.tenant.dataclass import FeatureFlags
from das.buoy.tests import generate_devices


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.skipif(FeatureFlags.buoy_api_enabled is False, reason="Buoy API feature flag is off")
class TestGearSerializer:
    def test_with_trawl_gear_subject(self, gear_subjectsource):
        gear_subjectsource.save()

        source = gear_subjectsource.source
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()
        additional = generate_devices(2)
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
       
        observation = Observation.objects.create(**data)
        observation.save()

        serialized_gear = GearsSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(gear_subjectsource.subject.id)
        assert serialized_gear["display_id"] == gear_subjectsource.subject.name
        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert gear_subjectsource.subject.is_active
        else:
            assert not gear_subjectsource.subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] in ("trawl", "single")
        assert serialized_gear["devices"] == observation.additional["devices"]
        assert len(serialized_gear["devices"]) == 2

    def test_with_single_gear_subject(self, gear_subjectsource):
        gear_subjectsource.save()

        source = gear_subjectsource.source
        provider = gear_subjectsource.source.provider
        provider.save()
        now = timezone.now()
        additional = generate_devices(1)
        location_dict = json.loads(additional["devices"][0])["location"]
        point = Point(location_dict["longitude"], location_dict["latitude"])
        data = {
            "recorded_at": now,
            "location": point,
            "source": source,
            "additional": additional,
        }
       
        observation = Observation.objects.create(**data)
        observation.save()

        serialized_gear = GearsSerializer(gear_subjectsource).data

        assert serialized_gear["id"] == str(gear_subjectsource.subject.id)
        assert serialized_gear["display_id"] == gear_subjectsource.subject.name if "display_id" not in observation.additional else observation.additional["display_id"]

        assert serialized_gear["state"] in ("deployed", "hauled")
        if serialized_gear["state"] == "deployed":
            assert gear_subjectsource.subject.is_active
        else:
            assert not gear_subjectsource.subject.is_active

        assert date_parser.parse(serialized_gear["last_updated"])
        assert serialized_gear["type"] == "single"
        assert serialized_gear["devices"] == observation.additional["devices"]
        assert len(serialized_gear["devices"]) == 1
