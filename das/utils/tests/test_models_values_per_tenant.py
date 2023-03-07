import pytest

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from choices.models import DynamicChoice
from utils.gis import convert_to_point


@pytest.mark.django_db
class TestActivityModelsValuesPerTenant:
    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "EventClass", "values": {"value": "same-value"}},
            {"model_name": "EventFactor", "values": {"value": "same-value"}},
            {"model_name": "EventRelationshipType", "values": {"value": "same-value"}},
            {
                "model_name": "EventType",
                "values": {"value": "same-value", "category_id": "ef230385-5afc-40d1-ad07-c811f6da2b3c"},
            },
            {"model_name": "MembershipType", "values": {"value": "same-value"}},
            {"model_name": "PatrolType", "values": {"value": "same-value"}},
        ],
    )
    def test_create_models_with_same_value_diff_tenant(self, data, five_tenants):
        model_class = apps.get_model("activity", data["model_name"])

        for tenant in five_tenants:
            model_class.objects.create(**data["values"], das_tenant=tenant)

        assert model_class.objects.filter(**data["values"], das_tenant__in=five_tenants).count() == 5

    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "EventCategory", "values": {}},
            {"model_name": "EventClass", "values": {}},
            {"model_name": "EventFactor", "values": {}},
            {"model_name": "EventRelationshipType", "values": {}},
            {"model_name": "EventType", "values": {"category_id": "ef230385-5afc-40d1-ad07-c811f6da2b3c"}},
            {"model_name": "MembershipType", "values": {}},
            {"model_name": "PatrolType", "values": {}},
        ],
    )
    def test_create_models_with_same_value_same_tenant(self, data, tenant_settings, das_tenant_monkeypatch):
        model_name = data["model_name"]
        model_class = apps.get_model("activity", model_name)

        with pytest.raises((IntegrityError, ValidationError)) as error:
            for _ in range(0, 2):
                model_class.objects.create(value="same-value", das_tenant=das_tenant_monkeypatch, **data["values"])

        assert f"activity_{model_name.lower()}_unique_value_across_tenants" in str(
            error
        ) or "Event Type with this Das tenant and Value already exists." in str(error)


@pytest.mark.django_db
class TestObservationsModelsValuesPerTenant:
    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "Region", "values": {"country": "Mexico", "region": "guadalajara"}},
            {"model_name": "SourceProvider", "values": {"provider_key": "same-provider-key"}},
        ],
    )
    def test_create_models_with_same_value_diff_tenant(self, data, five_tenants):
        model_name = data["model_name"]
        model_class = apps.get_model("observations", model_name)

        for tenant in five_tenants:
            model_class.objects.create(**data["values"], das_tenant=tenant)

        assert model_class.objects.filter(**data["values"], das_tenant__in=five_tenants).count() == 5

    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "Region", "field": "slug", "values": {"country": "Mexico", "region": "guadalajara"}},
            {"model_name": "SourceProvider", "field": "provider_key", "values": {"provider_key": "same-provider-key"}},
        ],
    )
    def test_create_models_with_same_value_same_tenant(self, data, das_tenant):
        model_name = data["model_name"]
        model_class = apps.get_model("observations", model_name)

        with pytest.raises(IntegrityError) as error:
            for _ in range(0, 2):
                model_class.objects.create(**data["values"], das_tenant=das_tenant)

        assert f"observations_{model_name.lower()}_unique_{data['field'].lower()}_across" in str(error)


@pytest.mark.django_db
class TestMappingModelsValuesPerTenant:
    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "ArcgisConfiguration", "values": {"config_name": "same-name"}},
            {"model_name": "DisplayCategory", "values": {"name": "same-name"}},
            {"model_name": "FeatureSet", "values": {"name": "same-name"}},
            {"model_name": "FeatureType", "values": {"name": "same-name"}},
            {"model_name": "Map", "values": {"name": "same-name", "center": convert_to_point("0,0"), "zoom": 0}},
            {"model_name": "SpatialFeatureGroupStatic", "values": {"name": "same-name"}},
            {"model_name": "SpatialFeatureType", "values": {"name": "same-name"}},
            {"model_name": "TileLayer", "values": {"name": "same-name"}},
        ],
    )
    def test_create_models_with_same_value_diff_tenant(self, data, five_tenants):
        model_name = data["model_name"]
        model_class = apps.get_model("mapping", model_name)

        for tenant in five_tenants:
            model_class.objects.create(**data["values"], das_tenant=tenant)

        assert model_class.objects.filter(**data["values"], das_tenant__in=five_tenants).count() == 5

    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "ArcgisConfiguration", "values": {"config_name": "same-name"}},
            {"model_name": "DisplayCategory", "values": {"name": "same-name"}},
            {"model_name": "FeatureSet", "values": {"name": "same-name"}},
            {"model_name": "FeatureType", "values": {"name": "same-name"}},
            {"model_name": "Map", "values": {"name": "same-name", "center": convert_to_point("0,0"), "zoom": 0}},
            {"model_name": "SpatialFeatureGroupStatic", "values": {"name": "same-name"}},
            {"model_name": "SpatialFeatureType", "values": {"name": "same-name"}},
            {"model_name": "TileLayer", "values": {"name": "same-name"}},
        ],
    )
    def test_create_models_with_same_value_same_tenant(self, data, das_tenant):
        model_name = data["model_name"]
        model_class = apps.get_model("mapping", model_name)

        with pytest.raises(IntegrityError) as error:
            for _ in range(0, 2):
                model_class.objects.create(**data["values"], das_tenant=das_tenant)

        assert f"mapping_{model_name.lower()}_unique_name_across_tenants" in str(error)


@pytest.mark.django_db
class TestChoicesModelsValuesPerTenant:
    def test_create_models_with_same_value_diff_tenant(self, five_tenants):
        name = "same-name"
        for tenant in five_tenants:
            DynamicChoice.objects.create(choice_name=name, das_tenant=tenant)

        assert DynamicChoice.objects.filter(choice_name=name, das_tenant__in=five_tenants).count() == 5

    def test_create_models_with_same_value_same_tenant(self, das_tenant):
        with pytest.raises(IntegrityError) as error:
            for _ in range(0, 2):
                DynamicChoice.objects.create(choice_name="same-name", das_tenant=das_tenant)

        assert "choices_dynamicchoice_unique_choice_name_across_tenants" in str(error)


@pytest.mark.django_db
class TestAnalyzersModelsValuesPerTenant:
    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "EnvironmentalSubjectAnalyzerConfig"},
            {"model_name": "FeatureProximityAnalyzerConfig"},
            {"model_name": "ImmobilityAnalyzerConfig"},
            {"model_name": "LowSpeedPercentileAnalyzerConfig"},
            {"model_name": "LowSpeedWilcoxAnalyzerConfig"},
            {"model_name": "SubjectProximityAnalyzerConfig"},
        ],
    )
    def test_create_models_with_same_value_diff_tenant(self, data, five_tenants, subject_group_empty):
        model_name = data["model_name"]
        model_class = apps.get_model("analyzers", model_name)

        name = "same-name"

        for tenant in five_tenants:
            kwargs = {"subject_group": subject_group_empty}
            if model_name == "SubjectProximityAnalyzerConfig":
                kwargs["second_subject_group"] = subject_group_empty

            model_class.objects.create(name=name, das_tenant=tenant, **kwargs)

        assert model_class.objects.filter(name=name, das_tenant__in=five_tenants).count() == 5

    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "EnvironmentalSubjectAnalyzerConfig"},
            {"model_name": "FeatureProximityAnalyzerConfig"},
            {"model_name": "ImmobilityAnalyzerConfig"},
            {"model_name": "LowSpeedPercentileAnalyzerConfig"},
            {"model_name": "LowSpeedWilcoxAnalyzerConfig"},
            {"model_name": "SubjectProximityAnalyzerConfig"},
        ],
    )
    def test_create_models_with_same_value_same_tenant(self, data, das_tenant, subject_group_empty):
        model_name = data["model_name"]
        model_class = apps.get_model("analyzers", model_name)

        with pytest.raises(IntegrityError) as error:
            for _ in range(0, 2):
                kwargs = {"subject_group": subject_group_empty}
                if model_name == "SubjectProximityAnalyzerConfig":
                    kwargs["second_subject_group"] = subject_group_empty

                model_class.objects.create(name="same-name", das_tenant=das_tenant, **kwargs)

        assert f"analyzers_{model_name.lower()}_unique_name_across" in str(error)


@pytest.mark.django_db
class TestTrackingModelsValuesPerTenant:
    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "AWETelemetryPlugin", "values": {"name": "same-name"}},
            {"model_name": "AWTHttpPlugin", "values": {"name": "same-name"}},
            {"model_name": "AwtPlugin", "values": {"name": "same-name"}},
            {"model_name": "DemoSourcePlugin", "values": {"name": "same-name"}},
            {"model_name": "FirmsPlugin", "values": {"name": "same-name"}},
            {"model_name": "InreachKMLPlugin", "values": {"name": "same-name"}},
            {"model_name": "InreachPlugin", "values": {"name": "same-name"}},
            {"model_name": "SavannahPlugin", "values": {"name": "same-name"}},
            {"model_name": "SirtrackPlugin", "values": {"name": "same-name"}},
            {"model_name": "SkygisticsSatellitePlugin", "values": {"name": "same-name"}},
            {"model_name": "SpiderTracksPlugin", "values": {"name": "same-name"}},
            {"model_name": "VectronicsPlugin", "values": {"name": "same-name"}},
        ],
    )
    def test_create_models_with_same_value_diff_tenant(self, data, five_tenants):
        model_name = data["model_name"]
        model_class = apps.get_model("tracking", model_name)

        for tenant in five_tenants:
            model_class.objects.create(**data["values"], das_tenant=tenant)

        assert model_class.objects.filter(**data["values"], das_tenant__in=five_tenants).count() == 5

    @pytest.mark.parametrize(
        "data",
        [
            {"model_name": "AWETelemetryPlugin", "values": {"name": "same-name"}},
            {"model_name": "AWTHttpPlugin", "values": {"name": "same-name"}},
            {"model_name": "AwtPlugin", "values": {"name": "same-name"}},
            {"model_name": "DemoSourcePlugin", "values": {"name": "same-name"}},
            {"model_name": "FirmsPlugin", "values": {"name": "same-name"}},
            {"model_name": "InreachKMLPlugin", "values": {"name": "same-name"}},
            {"model_name": "InreachPlugin", "values": {"name": "same-name"}},
            {"model_name": "SavannahPlugin", "values": {"name": "same-name"}},
            {"model_name": "SirtrackPlugin", "values": {"name": "same-name"}},
            {"model_name": "SkygisticsSatellitePlugin", "values": {"name": "same-name"}},
            {"model_name": "SpiderTracksPlugin", "values": {"name": "same-name"}},
            {"model_name": "VectronicsPlugin", "values": {"name": "same-name"}},
        ],
    )
    def test_create_models_with_same_value_same_tenant(self, data, das_tenant):
        model_name = data["model_name"]
        model_class = apps.get_model("tracking", model_name)

        with pytest.raises(IntegrityError) as error:
            for _ in range(0, 2):
                model_class.objects.create(**data["values"], das_tenant=das_tenant)

        assert f"tracking_{model_name.lower()}_unique_name_across_tenants" in str(error)
