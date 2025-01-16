import logging
import uuid
from typing import Optional

import simplejson as json
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from django.core.serializers import serialize
from django.urls import reverse
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

import utils
from choices.models import Choice
from core.serializers import BaseSerializer
from mapping.models import (
    FeatureType,
    Map,
    MBTiles,
    SpatialFeature,
    SpatialFeatureGroupStatic,
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


class FeatureTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureType
        fields = ("id", "name")  # , 'presentation',)


# from django.contrib.gis.geos import (
#     GeometryCollection, GEOSException, GEOSGeometry, LineString,
#     MultiLineString, MultiPoint, MultiPolygon, Point, Polygon,
# )


class SpatialFeatureListSerializer(GeoFeatureModelSerializer):
    feature_type_name = serializers.SerializerMethodField()
    feature_set_name = serializers.SerializerMethodField()
    feature_set_id = serializers.SerializerMethodField()

    class Meta:
        model = SpatialFeature
        geo_field = "feature_geometry"

        fields = (
            "id",
            "name",
            "short_name",
            "description",
            "feature_type_name",
            "feature_type_id",
            "feature_set_name",
            "feature_set_id",
        )

    def get_feature_type_name(self, obj: SpatialFeature) -> str:
        return obj.feature_type.name

    def get_feature_set_name(self, obj: SpatialFeature) -> Optional[str]:
        return obj.feature_type.display_category.name if obj.feature_type.display_category else None

    def get_feature_set_id(self, obj: SpatialFeature) -> Optional[uuid.UUID]:
        return obj.feature_type.display_category.id if obj.feature_type.display_category else None


class SpatialFeatureSerializer(serializers.ModelSerializer):
    # feature_geometry = FeatureGeometrySerializer()
    feature_type = FeatureTypeSerializer()

    class Meta:
        model = SpatialFeature
        fields = (
            "id",
            "name",
            "feature_type",
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


class SpatialFeatureGroupStaticSerializer(serializers.ModelSerializer):
    features = SpatialFeatureSerializer(many=True)

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ("name", "features", "description")

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        if "request" in self.context:
            rep["url"] = utils.add_base_url(
                self.context["request"],
                reverse(
                    "mapping:spatialfeaturegroup-view",
                    args=[
                        instance.id,
                    ],
                ),
            )

        return rep
