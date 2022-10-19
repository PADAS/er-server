import pytest

from django.core.exceptions import ValidationError
from django.test import RequestFactory

from activity.models import EventCategory
from factories import UserFactory
from utils.etags import get_hash_from_queryset


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetHashFromQueryset:
    @pytest.fixture
    def _request(self):
        user = UserFactory(id="8e4f0a57e6602bb45ee0f2a653badaa0")
        request = RequestFactory().get("/", headers={})
        request.user = user
        return request

    @pytest.mark.parametrize(
        ("fields", "expected_hash"),
        (
            (
                ["value", "display"],
                "320a52d0a2d815265bde629a6eb45e09",
            ),
            (
                ["value", "display", "ordernum"],
                "3a8ce5806a821122ee2b42022212c695",
            ),
            (
                ["value"],
                "b818f7934d47b0b64c9380a7833e0df7",
            ),
            (
                ["display"],
                "81d6ac7b8db05f78c6c13122df5e597f",
            ),
            (
                ["ordernum"],
                "13f260336e369d15cdbe1c2eb6ffce59",
            ),
        ),
    )
    def test_builder_by_one_instance(self, fields, expected_hash, five_event_categories, user, _request) -> None:
        obj = five_event_categories[0]

        queryset = EventCategory.objects.filter(pk=obj.pk).values(*fields)
        hash_string = get_hash_from_queryset(request=_request, queryset=queryset)

        assert isinstance(hash_string, str)
        assert hash_string == expected_hash

    def test_builder_hash_should_change(self, five_event_categories, _request) -> None:
        queryset = EventCategory.objects.values("value")
        hash_string = get_hash_from_queryset(queryset=queryset, request=_request)

        obj = five_event_categories[2]
        obj.value = "new_value"
        obj.save(update_fields=["value"])

        queryset = EventCategory.objects.values("value")
        new_hash_string = get_hash_from_queryset(queryset=queryset, request=_request)

        assert hash_string != new_hash_string

    def test_builder_num_queries(self, five_event_categories, django_assert_num_queries, _request) -> None:
        queryset = EventCategory.objects.values("value")

        with django_assert_num_queries(1):
            get_hash_from_queryset(queryset=queryset, request=_request)

    def test_raise_exception_when_queryset_not_called_values_method(self, five_event_categories, _request):
        queryset = EventCategory.objects.all()

        with pytest.raises(ValidationError):
            get_hash_from_queryset(queryset=queryset, request=_request)
