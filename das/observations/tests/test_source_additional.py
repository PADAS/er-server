import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytz

from django.contrib.gis.geos import Point
from django.test import TestCase

from choices.models import Choice
from observations.forms import SourceForm, SubjectSourceForm, generate_sample_data
from observations.models import (
    Observation,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
)
from observations.utils import convert_date_string


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SourceAdditionalTest(TestCase):
    def setUp(self):
        self.test_source_provider = SourceProvider.objects.create(
            provider_key="vectronics", display_name="vectronics", additional={}
        )
        Choice.objects.create(model="accounts.user.User", field="organization", value="KWS", display="KWS")

        Choice.objects.create(
            model="observations.Source", field="collar_status", value="Activated", display="Activated"
        )

    def test_source_additional_data(self):
        additional_data = {
            "collar_status": "Activated",
            "collar_model": "GPS",
            "collar_manufacturer": "Vectronics",
            "datasource": "SavannahTrackingAPI",
            "data_owners": ["KWS"],
            "adjusted_beacon_freq": "125",
            "frequency": "120",
            "adjusted_frequency": "40",
            "backup_frequency": "180",
            "predicted_expiry": "12/11/2018",
            "collar_key": "6484B8CA88E2B996421AB903D0B215AFAE285CAAE932F35F1",
        }
        form_data = {
            "id": uuid.uuid4(),
            "manufacturer_id": "32085",
            "provider": self.test_source_provider.id,
            "source_type": "tracking-device",
            "model_name": "GPSFix",
        }
        form_data = {**form_data, **additional_data}
        form = SourceForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()

        # Convert expiry date string into UTC format
        additional_data["predicted_expiry"] = convert_date_string(additional_data["predicted_expiry"])
        source, created = Source.objects.get_or_create(model_name="GPSFix")
        self.assertTrue(all(item in source.additional.items() for item in additional_data.items()))


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class SubjectSourceAdditionalTest(TestCase):
    def setUp(self):
        test_source_provider = SourceProvider.objects.create(
            provider_key="vectronics", display_name="vectronics", additional={}
        )

        Choice.objects.create(model="accounts.user.User", field="organization", value="KWS", display="KWS")
        Choice.objects.create(
            model="observations.Source", field="collar_status", value="Activated", display="Activated"
        )

        additional_data = {
            "collar_status": "Activated",
            "collar_model": "GPS",
            "collar_manufacturer": "Vectronics",
            "datasource": "SavannahTrackingAPI",
            "data_owners": ["KWS"],
            "adjusted_beacon_freq": "125",
            "frequency": "120",
            "adjusted_frequency": "40",
            "backup_frequency": "180",
            "predicted_expiry": "12/11/2018",
            "collar_key": "6484B8CA88E2B996421AB903D0B215AFAE285CAAE932F35F1",
        }
        form_data = {
            "id": uuid.uuid4(),
            "manufacturer_id": "32085",
            "provider": test_source_provider.id,
            "source_type": "tracking-device",
            "model_name": "GPSFix",
        }
        form_data = {**form_data, **additional_data}
        form = SourceForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()
        self.source, created = Source.objects.get_or_create(model_name="GPSFix")

        Choice.objects.create(
            model="observations.Source", field="data stops reason", value="Damaged", display="Collar Damaged"
        )

        self.henry = Subject.objects.create(name="Henry")

    def test_subjectsource_additional_data(self):
        start_date = datetime.now(timezone.utc) - timedelta(days=200)
        end_date = datetime.now(timezone.utc)
        form_data = {
            "id": uuid.uuid4(),
            "subject": self.henry.id,
            "source": self.source.id,
            "assigned_range_0": start_date.isoformat(),
            "assigned_range_1": end_date.isoformat(),
            "location": Point(1, 1),
        }
        additional_data = {"data_status": "Activated", "data_stops_reason": "Damaged"}
        form_data = {**form_data, **additional_data}
        form = SubjectSourceForm(data=form_data)
        self.assertTrue(form.is_valid())
        form.save()
        subject_source = SubjectSource.objects.get(subject=self.henry)
        self.assertTrue(all(item in subject_source.additional.items() for item in additional_data.items()))


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
@pytest.mark.parametrize(
    "additional",
    [
        {"speed": 50, "temperature": 15},
        {
            "Fuel": "52L",
            "Speed": 0.0,
            "Address": "Sweetwaters, Thuthuriki, Laikipia County, Kenya (Kamok Residence) [0.06242 / 36.8127]",
            "Odometer": 489763.4,
            "EngineStatus": "stopped",
        },
    ],
)
def test_generate_sample_data(subject_source, additional):
    source_provider = subject_source.source.provider
    Observation.objects.create(
        source=subject_source.source,
        location=Point(-103.5, 20.5),
        recorded_at=datetime.now(tz=pytz.utc),
        additional=additional,
    )

    data = generate_sample_data(source_provider)

    for key, value in additional.items():
        assert key in data
        assert isinstance(data[key], list)
        assert value in data[key]
