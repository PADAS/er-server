from datetime import datetime

import pytest

from django.contrib.auth import get_user_model

from sensors.serializers import SensorPostParameters

User = get_user_model()


@pytest.mark.django_db
class TestSensorPostParameters:
    data = {
        "location": {"lat": 20.798100674730364, "long": 18.245000626939387},
        "recorded_at": datetime.today(),
        "manufacturer_id": "manufacturer",
        "subject_id": "223503b9-9cd7-4933-b19d-a0301fc98036",
        "subject_name": "dumbo",
        "subject_groups": ["another"],
        "subject_type": "subject_type",
        "subject_subtype": "subject_subtype",
        "subject_additional": {},
        "model_name": "model_name",
        "source_type": "source_type",
        "additional": {"key": "value"},
        "source_additional": {},
        "user_id": "82794df0-afa6-469d-8fce-8db556707e64",
    }

    def test_serialized_sensor_post_parameter_format(self, ops_user, subject):
        self.data["user_id"] = str(ops_user.id)
        self.data["subject_id"] = str(subject.id)
        serialized_sensor = SensorPostParameters(data=self.data)
        serialized_sensor.is_valid()
        serialized_data = serialized_sensor.data

        assert isinstance(serialized_data["location"]["lat"], float)
        assert isinstance(serialized_data["location"]["long"], float)
        assert isinstance(serialized_data["recorded_at"], str)
        assert isinstance(serialized_data["manufacturer_id"], str)
        assert isinstance(serialized_data["subject_id"], str)
        assert isinstance(serialized_data["subject_name"], str)
        assert isinstance(serialized_data["subject_groups"], list)
        assert isinstance(serialized_data["subject_type"], str)
        assert isinstance(serialized_data["subject_subtype"], str)
        assert isinstance(serialized_data["subject_additional"], dict)
        assert isinstance(serialized_data["model_name"], str)
        assert isinstance(serialized_data["source_type"], str)
        assert isinstance(serialized_data["additional"], dict)
        assert isinstance(serialized_data["source_additional"], dict)
        assert isinstance(serialized_data["user_id"], str)

    def test_serialized_sensor_post_parameter(self, ops_user, subject):
        self.data["user_id"] = str(ops_user.id)
        self.data["subject_id"] = str(subject.id)
        serialized_sensor = SensorPostParameters(data=self.data)
        serialized_sensor.is_valid()
        serialized_data = serialized_sensor.data

        assert serialized_data["location"] == {"lat": 20.798100674730364, "long": 18.245000626939387}
        assert serialized_data["recorded_at"] == self.data["recorded_at"].astimezone().isoformat()
        assert serialized_data["manufacturer_id"] == "manufacturer"
        assert serialized_data["subject_id"] == str(subject.id)
        assert serialized_data["subject_name"] == "dumbo"
        assert serialized_data["subject_groups"] == ["another"]
        assert serialized_data["subject_type"] == "subject_type"
        assert serialized_data["subject_subtype"] == "subject_subtype"
        assert serialized_data["subject_additional"] == {}
        assert serialized_data["model_name"] == "model_name"
        assert serialized_data["source_type"] == "source_type"
        assert serialized_data["additional"] == {"key": "value"}
        assert serialized_data["source_additional"] == {}
        assert serialized_data["user_id"] == str(ops_user.id)

    def test_validate_wrong_linked_subject_to_user(self, ops_user, five_subjects):
        subject = five_subjects[0]
        fake_subject = five_subjects[1]
        subject.linked_user = ops_user
        subject.save()
        self.data["subject_id"] = str(fake_subject.id)
        self.data["user_id"] = str(ops_user.id)

        serialized_sensor = SensorPostParameters(data=self.data)
        serialized_sensor.is_valid()

        assert serialized_sensor.errors["non_field_errors"][0] == "The subject is not linked to the user."

    def test_validate_when_subject_is_already_linked_to_another_user(self, ops_user, subject, superuser):
        subject.linked_user = superuser
        subject.save()
        self.data["subject_id"] = str(subject.id)
        self.data["user_id"] = str(ops_user.id)

        serialized_sensor = SensorPostParameters(data=self.data)
        serialized_sensor.is_valid()

        assert serialized_sensor.errors["non_field_errors"][0] == "The subject is linked to another user."

    def test_validate_user_id_does_not_exists(self):
        self.data["user_id"] = "dc8fe87e-e64f-40b4-bde4-d68e453b6d2f"

        serialized_sensor = SensorPostParameters(data=self.data)
        serialized_sensor.is_valid()

        assert (
            serialized_sensor.errors["user_id"][0]
            == "The user with id dc8fe87e-e64f-40b4-bde4-d68e453b6d2f does not exists."
        )
