import pytest

from django.core.exceptions import FieldError

from utils.etags import HashByModelBuilder


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestHashByModelBuilder:

    @pytest.mark.parametrize(
        ("fields", "expected_hash"),
        (
            (
                ["value", "display"],
                "d7ebca9015724a7fdaf3a011e1a683a7",
            ),
            (
                ["value", "display", "ordernum"],
                "56ff8f3a062c37b8d690513771949324",
            ),
            (
                ["value"],
                "9f09f7aa05db684bca72cd379826b607",
            ),
            (
                ["display"],
                "e008a09c8f5517fd06350d9c3a884ce6",
            ),
            (
                ["ordernum"],
                "7d6a9b36ce5b8d5a6d8f5d2c3fd1befd",
            ),
        ),
    )
    def test_builder_by_one_instance(self, fields, expected_hash, five_event_categories) -> None:
        obj = five_event_categories[0]
        builder = HashByModelBuilder(model=obj.__class__, pk=obj.pk, field_names=fields)
        hash_string = builder.build()

        assert isinstance(hash_string, str)
        assert hash_string == expected_hash

    def test_builder_m2m_related_fields(self, five_event_categories) -> None:
        obj = five_event_categories[1]
        builder = HashByModelBuilder(model=obj.__class__, field_names=["value"])
        builder.set_m2m_related_model_string(relation_name="eventtype_set", field_names=["display"])
        hash_string = builder.build()

        assert hash_string == "e667be477ccfc1e65aeb2b3369422d2c"

    def test_builder_using_filters(self, five_event_categories) -> None:
        obj = five_event_categories[1]
        builder = HashByModelBuilder(
            model=obj.__class__, field_names=["value", "display"], filter_opts={"value": obj.value}
        )
        hash_string = builder.build()

        assert hash_string == "ab60468a2f5133687441f0342a61ca0d"

    def test_builder_hash_should_change(self, five_event_categories) -> None:
        obj = five_event_categories[2]
        builder = HashByModelBuilder(model=obj.__class__, field_names=["value"])
        hash_string = builder.build()

        assert hash_string == "6045fab9124577b22035681b9c24686a"

        obj.value = "new_value"
        obj.save(update_fields=["value"])

        builder = HashByModelBuilder(model=obj.__class__, field_names=["value"])
        new_hash_string = builder.build()

        assert new_hash_string == "444e7c3f93364c6643f8fb9d75b7f81c"
        assert hash_string != new_hash_string

    def test_builder_receive_wrong_fields(self, five_event_categories) -> None:
        obj = five_event_categories[3]

        with pytest.raises(FieldError):
            builder = HashByModelBuilder(model=obj.__class__, field_names=["wrong_value"])
            builder.build()

    def test_builder_num_queries(self, five_event_categories, django_assert_num_queries) -> None:
        obj = five_event_categories[3]

        with django_assert_num_queries(1):
            builder = HashByModelBuilder(model=obj.__class__, field_names=["value"])
            builder.build()
