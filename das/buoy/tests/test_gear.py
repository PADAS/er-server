import pytest

from das.buoy.serializers import GearSerializer


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGearSerializer:
    def test_with_subject(self, subject):
        subject.save()

        serialized_gear = GearSerializer(subject).data

        assert serialized_gear["id"]
        assert serialized_gear["display_id"]
        assert serialized_gear["state"]
        assert serialized_gear["last_updated"]

    # TODO: Come up with test cases to debug more scnearios
    # def test_without_linked_user(self, subject):
    #     serialized_subject = GearSerializer(subject).data

    #     assert not serialized_subject["user"]
