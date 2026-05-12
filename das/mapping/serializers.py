from __future__ import annotations

import logging
import uuid
from typing import Any

import simplejson as json
from rest_framework_gis.fields import GeometryField

from django.core.serializers import serialize
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from choices.models import Choice
from core.serializers import BaseSerializer
from mapping.models import (
    DisplayCategory,
    FeatureType,
    Map,
    MBTiles,
    SpatialFeature,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
    TileLayer,
)

logger = logging.getLogger(__name__)


class MBTilesSerializer(serializers.Serializer):
    def to_representation(self, instance):
        mbtiles_name = instance.attributes["mbtiles_name"]
        mbtiles = MBTiles(mbtiles_name)
        request = self.context["request"]
        return mbtiles.tilejson(request)


class ExternalTileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TileLayer
        fields = ("id", "name", "attributes", "ordernum")

    def to_representation(self, instance):
        rep = super(ExternalTileSerializer, self).to_representation(instance)
        # rep.update(instance.attributes)
        return rep


class ServiceTypeRelatedField(serializers.RelatedField):
    def get_queryset(self):
        return Choice.objects.filter(model="mapping.TileLayer", field="service_type")

    def to_representation(self, value):
        return value.value if value else None

    def to_internal_value(self, data):
        if data:
            try:
                Choice.objects.get(value=data)
                return data
            except Choice.DoesNotExist:
                raise serializers.ValidationError({"choice": f"Choice with value {data} does not exist."})
        return None

    def display_value(self, instance):
        return instance.display


class TileLayerAttributes(serializers.Serializer):
    type = ServiceTypeRelatedField(required=False, allow_empty=True)
    title = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    icon_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    configuration = serializers.JSONField(required=False, allow_null=True, default=dict)


class TileLayerSerializer(BaseSerializer):
    id = serializers.UUIDField(required=False, read_only=True)
    name = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[UniqueValidator(queryset=TileLayer.objects.all())],
    )
    ordernum = serializers.IntegerField(required=False, allow_null=True)
    attributes = TileLayerAttributes()

    def to_representation(self, instance):
        request = self.context["request"]

        rep = ExternalTileSerializer(instance, context={"request": request})
        return rep.data

    def create(self, validated_data):
        return TileLayer.objects.create(**validated_data)


class MapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Map
        fields = ("id", "name", "zoom")

    def to_representation(self, instance):
        rep = super(MapSerializer, self).to_representation(instance)
        rep.update(instance.attributes)
        rep["center"] = instance.center.tuple

        return rep


class MapWriteSerializer(serializers.ModelSerializer):
    center = GeometryField()

    class Meta:
        model = Map
        fields = ("id", "name", "center", "zoom", "attributes")
        read_only_fields = ("id",)


class FeatureTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureType
        fields = ("id", "name")  # , 'presentation',)


class SpatialFeatureTypeSerializer(serializers.ModelSerializer):
    feature_set_id = serializers.UUIDField(source="display_category_id")

    class Meta:
        model = SpatialFeatureType
        fields = ("id", "name", "feature_set_id")


# from django.contrib.gis.geos import (
#     GeometryCollection, GEOSException, GEOSGeometry, LineString,
#     MultiLineString, MultiPoint, MultiPolygon, Point, Polygon,
# )


class SpatialFeatureListSerializer(serializers.ModelSerializer):
    feature_class_name = serializers.SerializerMethodField()
    feature_class_id = serializers.SerializerMethodField()
    feature_set_name = serializers.SerializerMethodField()
    feature_set_id = serializers.SerializerMethodField()
    url = serializers.HyperlinkedIdentityField(view_name="mapping_v2:feature-detail", lookup_field="id")

    class Meta:
        model = SpatialFeature
        fields = (
            "id",
            "name",
            "short_name",
            "description",
            "feature_class_name",
            "feature_class_id",
            "feature_set_name",
            "feature_set_id",
            "url",
        )

    def get_feature_class_name(self, obj: SpatialFeature) -> str:
        return obj.feature_type.name

    def get_feature_class_id(self, obj: SpatialFeature) -> uuid.UUID:
        return obj.feature_type.id

    def get_feature_set_name(self, obj: SpatialFeature) -> str | None:
        return obj.feature_type.display_category.name if obj.feature_type.display_category else None

    def get_feature_set_id(self, obj: SpatialFeature) -> uuid.UUID | None:
        return obj.feature_type.display_category.id if obj.feature_type.display_category else None


class SpatialFeatureSerializer(serializers.ModelSerializer):
    # feature_geometry = FeatureGeometrySerializer()
    feature_class = FeatureTypeSerializer()

    class Meta:
        model = SpatialFeature
        fields = (
            "id",
            "name",
            "feature_class",
            # 'feature_geometry',
        )

    def to_representation(self, instance):
        # rep = super().to_representation(instance)
        return json.loads(
            serialize(
                "geojson",
                (instance,),
                properties={},
                geometry_field="feature_geometry",
            )
        )


class SpatialFeatureGroupListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list endpoints - excludes expensive features field."""

    url = serializers.HyperlinkedIdentityField(view_name="mapping:featuregroups-detail", lookup_field="id")
    feature_count = serializers.SerializerMethodField()

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ("id", "name", "description", "url", "feature_count")

    def get_feature_count(self, obj: SpatialFeatureGroupStatic) -> int:
        return getattr(obj, "feature_count", obj.features.count())


class SpatialFeatureGroupDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for detail endpoints - includes full feature data."""

    url = serializers.HyperlinkedIdentityField(view_name="mapping:featuregroups-detail", lookup_field="id")
    features = SpatialFeatureSerializer(many=True)
    feature_count = serializers.SerializerMethodField()

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ("id", "name", "description", "url", "features", "feature_count", "created_at", "updated_at")

    def get_feature_count(self, obj: SpatialFeatureGroupStatic) -> int:
        return getattr(obj, "feature_count", obj.features.count())


class DisplayCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplayCategory
        fields = ("id", "name", "description")
        read_only_fields = ("id",)


class SpatialFeatureTypeWriteSerializer(serializers.ModelSerializer):
    display_category = serializers.PrimaryKeyRelatedField(
        queryset=DisplayCategory.objects, allow_null=True, required=False
    )

    class Meta:
        model = SpatialFeatureType
        fields = ("id", "name", "display_category", "presentation", "attribute_schema", "is_visible")
        read_only_fields = ("id",)


class SpatialFeatureWriteSerializer(serializers.ModelSerializer):
    feature_type = serializers.PrimaryKeyRelatedField(queryset=SpatialFeatureType.objects)
    feature_geometry = GeometryField()

    class Meta:
        model = SpatialFeature
        fields = (
            "id",
            "feature_type",
            "name",
            "short_name",
            "description",
            "feature_geometry",
            "presentation",
            "attributes",
            "provenance",
        )
        read_only_fields = ("id",)

    def create(self, validated_data: dict[str, Any]) -> SpatialFeature:
        instance = SpatialFeature(**validated_data)
        instance.clean()
        instance.save()
        return instance

    def update(self, instance: SpatialFeature, validated_data: dict[str, Any]) -> SpatialFeature:
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.clean()
        instance.save()
        return instance


class SpatialFeatureGroupWriteSerializer(serializers.ModelSerializer):
    features = serializers.PrimaryKeyRelatedField(many=True, queryset=SpatialFeature.objects, required=False)

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ("id", "name", "description", "features")
        read_only_fields = ("id",)

    def create(self, validated_data: dict[str, Any]) -> SpatialFeatureGroupStatic:
        features = validated_data.pop("features", [])
        instance = SpatialFeatureGroupStatic.objects.create(**validated_data)
        instance.features.set(features)
        return instance

    def update(self, instance: SpatialFeatureGroupStatic, validated_data: dict[str, Any]) -> SpatialFeatureGroupStatic:
        features = validated_data.pop("features", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if features is not None:
            instance.features.set(features)
        return instance
