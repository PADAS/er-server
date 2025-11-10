import datetime
import glob
import logging
import os
import uuid
from typing import List

import tagulous.settings
from django_multitenant.fields import TenantForeignKey
from django_multitenant.mixins import TenantManagerMixin, TenantModelMixin
from pytz import timezone
from tagulous.models import TagField as TagulousTagField
from tagulous.models import TagModel

from django.conf import settings
from django.contrib.gis import geos
from django.contrib.gis.db import models
from django.core.cache import cache
from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.storage import FileSystemStorage
from django.db.models import Index, Q, UniqueConstraint
from django.urls import NoReverseMatch, reverse
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from core.models import DASTenant, TimestampedModel, UUIDModel
from mapping.app_settings import MBTILES
from mapping.cache import bump_vector_tile_data_version
from mapping.lookups import (
    GEO_TYPE_LINESTRING,
    GEO_TYPE_MULTILINESTRING,
    GEO_TYPE_MULTIPOINT,
    GEO_TYPE_MULTIPOLYGON,
    GEO_TYPE_POINT,
    GEO_TYPE_POLYGON,
    GeometryTypeLookup,
)
from mapping.mbtiles import (
    ExtractionError,
    GoogleProjection,
    InvalidFormatError,
    MBTilesReader,
)
from mapping.utils import SPATIAL_FILES_FOLDER, check_file_extension
from revision.manager import Revision, RevisionMixin
from utils.decorator import reify
from utils.migrations.columns import default_tenant_id
from utils.models import CommonTenantManager
from utils.tenant.models import TenantThroughModel
from utils.tenant.thread import get_tenant_settings

logger = logging.getLogger(__name__)

# Ensure the custom lookup is registered
GeometryField.register_lookup(GeometryTypeLookup)

FILE_TYPES = (
    ("shapefile", "Shapefile"),
    # Commenting out geodatabase for now, until we can verify functionality with a .gdb file.
    # ('geodatabase', 'Geodatabase'),
    ("geojson", "GeoJSON"),
)


class MapManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class Map(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict, blank=True)
    center = models.PointField(srid=4326)
    zoom = models.IntegerField()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = MapManager()

    class Meta:
        verbose_name = "Map Quicklink"
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"], name="%(app_label)s_%(class)s_name_idx")]

    def __str__(self):
        return self.name


class TileLayerQuerySet(models.QuerySet):
    def by_ordernum(self):
        return self.order_by("ordernum", "name")


class TileLayerManager(TenantManagerMixin, models.Manager.from_queryset(TileLayerQuerySet)):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class TileLayer(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    attributes = models.JSONField(default=dict, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = TileLayerManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        verbose_name = "Basemap"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"], name="%(app_label)s_%(class)s_name_idx")]

    def __str__(self):
        return self.name


class FeatureTypeManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class FeatureType(TenantModelMixin, TimestampedModel):
    """
    If the clients wish to group layers in a control or for ease of administration

    MapBox convention for stylization of feature types:
    Points: https://www.mapbox.com/mapbox-gl-style-spec/#layers-symbol
    Lines: https://www.mapbox.com/mapbox-gl-style-spec/#layers-line
    Polygons: https://www.mapbox.com/mapbox-gl-style-spec/#layers-fill
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    presentation = models.JSONField(default=dict, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = FeatureTypeManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"], name="%(app_label)s_%(class)s_name_idx")]

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)

    @property
    def feature_count(self):
        return (
            PolygonFeature.objects.filter(type=self).count()
            + LineFeature.objects.filter(type=self).count()
            + PointFeature.objects.filter(type=self).count()
        )


class FeatureSetManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class FeatureSet(TenantModelMixin, TimestampedModel):
    """
    A grouping of features that should be toggled together on the map,
      e.g. a set of camps or a system of rivers
      ... better than handling as a layer group in UI as it allows grouping to be controlled in db?
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    types = models.ManyToManyField(
        to=FeatureType,
        related_name="feature_sets",
        through="mapping.FeatureSetFeatureType",
        through_fields=("featureset", "featuretype"),
    )
    description = models.TextField(null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = FeatureSetManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"])]

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


class FeatureSetFeatureType(TenantModelMixin, UUIDModel):
    """
    Intermediate model to store the many-to-many relationship between FeatureSets and FeatureTypes
    """

    featureset = TenantForeignKey(FeatureSet, on_delete=models.CASCADE)
    featuretype = TenantForeignKey(FeatureType, on_delete=models.CASCADE)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = CommonTenantManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "featureset", "featuretype"],
                name="%(app_label)s_%(class)s_unique_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "featureset"]), Index(fields=["das_tenant", "featuretype"])]


@deconstructible
class TempStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        import tempfile

        temp_directory_name = tempfile.mkdtemp()
        kwargs.update(
            {
                "location": temp_directory_name,
            }
        )
        super(TempStorage, self).__init__(**kwargs)


def upload_to(instance, filename):
    """
    Providing a path to an Spatialfiles.
    :param instance: SpatialFile of SpatialFeatureFile instance
    :param filename: default filename.
    :return: relative path for storing uploaded file
    """
    filename = filename.split("/")[-1]
    timestamp = "{:%Y%m%d%H%s}".format(datetime.datetime.now())
    tenant = get_tenant_settings()
    file_path = f"{tenant.slug_name}/{SPATIAL_FILES_FOLDER}/{timestamp}-{filename}"
    return file_path


class SpatialFileBaseManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFilesBase(TenantModelMixin, TimestampedModel):
    """
    Base model for uploading Spatial files such as shapefile
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, blank=True, verbose_name="SpatialFile Name")
    description = models.CharField(max_length=100, blank=True)
    data = models.FileField(upload_to=upload_to, blank=False)
    layer_number = models.IntegerField(blank=True, null=True, default=0)
    name_field = models.CharField(max_length=100, blank=True, null=True)
    id_field = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=1000, blank=True, null=True, verbose_name="Feature Load Status")
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = SpatialFileBaseManager()

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"

    # Clean method is used for better error handling within the admin form
    # itself. To have the file data available, save method needs to be invoked.
    #  Cleanup method will remove files in case of validation error.
    # Can a better way be utilized which avoids saving the Spatial file model?

    def clean(self):
        """
        Overwriting clean method to have error handling within the admin form.
        """
        if not self.data:
            raise ValidationError({"data": []})

        feature_types_file = getattr(self, "feature_types_file", None)
        file_type = getattr(self, "file_type", None)

        if file_type:
            check_file_extension(self.file_type, self.data, feature_types_file)

    def __str__(self):
        return str(self.id)


class SpatialFile(SpatialFilesBase):
    """
    Geometry type [polygon, line, point] loaded from uploaded shapefile
    INFO TenantModelMixin covered by abstract class
    """

    feature_set = TenantForeignKey(to=FeatureSet, on_delete=models.PROTECT)
    feature_type = TenantForeignKey(to=FeatureType, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Spatial File"


class FeatureManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class Feature(TenantModelMixin, TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    type = TenantForeignKey(to=FeatureType, on_delete=models.PROTECT)
    description = models.TextField(null=True, blank=True)
    # attributes for presentation
    presentation = models.JSONField(default=dict, blank=True)
    fields = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)
    # the feature set with which this feature is being grouped.
    # todo:  evaluate whether many-to-many might be a better approach or stick
    # with this simple approach
    # probably should be spelled feature_set
    featureset = TenantForeignKey(to=FeatureSet, null=True, on_delete=models.PROTECT)
    spatialfile = TenantForeignKey(to=SpatialFile, null=True, blank=True, on_delete=models.SET_NULL)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"

    objects = FeatureManager()

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        if self.type.presentation:
            return self.type.presentation
        return {}

    class Meta:
        abstract = True
        ordering = ["name"]
        base_manager_name = "objects"
        default_manager_name = "objects"

    # todo:  perhaps type and name?
    def __str__(self):
        return "{0}".format(self.name)


class PolygonFeature(Feature):
    feature_geometry = models.MultiPolygonField(srid=4326)


class LineFeature(Feature):
    feature_geometry = models.MultiLineStringField(srid=4326)


class PointFeature(Feature):
    feature_geometry = models.MultiPointField(srid=4326)


class MissingTileError(Exception):
    pass


class MBTilesNotFoundError(Exception):
    pass


class MBTilesFolderError(ImproperlyConfigured):
    def __init__(self, *args, **kwargs):
        super(ImproperlyConfigured, self).__init__(_("MBTILES['root'] '%s' does not exist") % MBTILES["root"])


class MBTilesManager(object):
    """List available MBTiles in MBTILES['root']
    source: https://github.com/makinacorpus/django-mbtiles.git
    license: Lesser GNU Public License
    """

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not os.path.exists(MBTILES["root"]):
            self.logger.error("MBTILES folder not set %s", MBTilesFolderError())
        self.folder = MBTILES["root"]

    def filter(self, catalog=None):
        if catalog:
            self.folder = self.catalog_path(catalog)
        return self

    def all(self):
        return self

    def __iter__(self):
        filepattern = os.path.join(self.folder, "*.%s" % MBTILES["ext"])
        for filename in glob.glob(filepattern):
            name, ext = os.path.splitext(filename)
            try:
                mb = MBTiles(os.path.join(self.folder, filename))
                assert mb.name, _("%s name is empty !") % mb.id
                yield mb
            except (AssertionError, InvalidFormatError) as e:
                logger.error(e)

    @property
    def _subfolders(self):
        for dirname, dirnames, filenames in os.walk(MBTILES["root"]):
            return dirnames
        return []

    def default_catalog(self):
        if len(list(self)) == 0 and len(self._subfolders) > 0:
            return self._subfolders[0]
        return None

    def catalog_path(self, catalog=None):
        if catalog is None:
            return MBTILES["root"]
        path = os.path.join(MBTILES["root"], catalog)
        if os.path.exists(path):
            return path
        raise MBTilesNotFoundError(_("Catalog '%s' not found.") % catalog)

    def fullpath(self, name, catalog=None):
        if os.path.exists(name):
            return name

        if catalog is None:
            basepath = self.folder
        else:
            basepath = self.catalog_path(catalog)

        mbtiles_file = os.path.join(basepath, name)
        if os.path.exists(mbtiles_file):
            return mbtiles_file

        mbtiles_file = "%s.%s" % (mbtiles_file, MBTILES["ext"])
        if os.path.exists(mbtiles_file):
            return mbtiles_file

        raise MBTilesNotFoundError(_("'%s' not found in %s") % (mbtiles_file, basepath))


class MBTiles(object):
    """Represent a MBTiles file"""

    objects = MBTilesManager()

    def __init__(self, name, catalog=None):
        self.catalog = catalog
        self.fullpath = self.objects.fullpath(name, catalog)
        self.basename = os.path.basename(self.fullpath)
        self._reader = MBTilesReader(self.fullpath, tilesize=MBTILES["tile_size"])

    @property
    def id(self):
        iD, ext = os.path.splitext(self.basename)
        return iD

    @property
    def name(self):
        return self.metadata.get("name", self.id)

    @property
    def filesize(self):
        return os.path.getsize(self.fullpath)

    @reify
    def metadata(self):
        return self._reader.metadata()

    @reify
    def bounds(self):
        bounds = self.metadata.get("bounds", "").split(",")
        if len(bounds) != 4:
            logger.warning(_("Invalid bounds metadata in '%s', fallback to whole world.") % self.name)
            bounds = [-180, -90, 180, 90]
        return tuple(map(float, bounds))

    @reify
    def center(self):
        """
        Return the center (x,y) of the map at this zoom level.
        """
        center = self.metadata.get("center", "").split(",")
        if len(center) == 3:
            lon, lat, zoom = map(float, center)
            zoom = int(zoom)
            if zoom not in self.zoomlevels:
                logger.warning(_("Invalid zoom level (%s), fallback to middle zoom (%s)") % (zoom, self.middlezoom))
                zoom = self.middlezoom
            return (lon, lat, zoom)
        # Invalid center from metadata, guess center from bounds
        lat = self.bounds[1] + (self.bounds[3] - self.bounds[1]) / 2
        lon = self.bounds[0] + (self.bounds[2] - self.bounds[0]) / 2
        return (lon, lat, self.middlezoom)

    @property
    def minzoom(self):
        z = self.metadata.get("minzoom", self.zoomlevels[0])
        return int(z)

    @property
    def maxzoom(self):
        z = self.metadata.get("maxzoom", self.zoomlevels[-1])
        return int(z)

    @property
    def middlezoom(self):
        return self.zoomlevels[int(len(self.zoomlevels) / 2)]

    @reify
    def zoomlevels(self):
        return self._reader.zoomlevels()

    def tile(self, z, x, y):
        try:
            return self._reader.tile(z, x, y)
        except ExtractionError:
            raise MissingTileError

    def center_tile(self):
        lon, lat, zoom = self.center
        proj = GoogleProjection(MBTILES["tile_size"], [zoom])
        return proj.tile_at(zoom, (lon, lat))

    def grid(self, z, x, y, callback=None):
        try:
            return self._reader.grid(z, x, y, callback)
        except ExtractionError:
            raise MissingTileError

    def tilejson(self, request):
        # Raw metadata
        jsonp = dict(self.metadata)
        # Post-processed metadata
        jsonp.update(
            **{
                "bounds": self.bounds,
                "center": self.center,
                "minzoom": self.minzoom,
                "maxzoom": self.maxzoom,
                "autoscale": False,
            }
        )
        # Additionnal info
        try:
            kwargs = dict(name=self.id, x="{x}", y="{y}", z="{z}")
            if self.catalog:
                kwargs["catalog"] = self.catalog
            tilepattern = reverse("mapping:tile", kwargs=kwargs)
            gridpattern = reverse("mapping:grid", kwargs=kwargs)
        except NoReverseMatch:
            # In case django-mbtiles was not registered in namespace mbtilesmap
            tilepattern = reverse("tile", kwargs=dict(name=self.id, x="{x}", y="{y}", z="{z}"))
            gridpattern = reverse("grid", kwargs=dict(name=self.id, x="{x}", y="{y}", z="{z}"))
        tilepattern = request.build_absolute_uri(tilepattern)
        gridpattern = request.build_absolute_uri(gridpattern)
        tilepattern = tilepattern.replace("%7B", "{").replace("%7D", "}")
        gridpattern = gridpattern.replace("%7B", "{").replace("%7D", "}")
        jsonp.update(
            **{
                "tilejson": "2.1.0",
                "id": self.id,
                "name": self.name,
                "scheme": "xyz",
                "basename": self.basename,
                "filesize": self.filesize,
                "tiles": [tilepattern],
                "grids": [gridpattern],
            }
        )
        return jsonp


"""Below are new classes proposed by Jake for structuring spatial data in DAS"""


class SpatialFeatureGroupManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureGroupStaticFeatures(TenantThroughModel):
    spatial_feature_groupstatic = TenantForeignKey(
        "mapping.SpatialFeatureGroupStatic",
        on_delete=models.CASCADE,
    )
    spatial_feature = TenantForeignKey(
        "mapping.SpatialFeature",
        on_delete=models.CASCADE,
    )


class SpatialFeatureGroupStaticQuerySet(models.QuerySet):
    def by_spatial_type(self, spatial_types: List[str], exclusive: bool = True):
        ALL_FEATURE_TYPES = (
            GEO_TYPE_POINT,
            GEO_TYPE_LINESTRING,
            GEO_TYPE_POLYGON,
            GEO_TYPE_MULTIPOINT,
            GEO_TYPE_MULTILINESTRING,
            GEO_TYPE_MULTIPOLYGON,
        )
        queryset = self
        if exclusive:
            # For exclusive mode, we want groups that:
            # 1. Have at least one feature with a desired spatial type
            # 2. Have NO features with unwanted spatial types
            # django doesn't support feature_geometry__type__in, so we have to use Q objects
            unwanted_types = [type for type in ALL_FEATURE_TYPES if type not in spatial_types]

            # Build Q objects for desired types (OR conditions)
            desired_q = Q()
            for spatial_type in spatial_types:
                desired_q |= Q(features__feature_geometry__type=spatial_type)

            # Build Q objects for unwanted types (OR conditions)
            unwanted_q = Q()
            for unwanted_type in unwanted_types:
                unwanted_q |= Q(features__feature_geometry__type=unwanted_type)

            # First, get groups that have at least one feature with desired types
            queryset_with_desired = queryset.filter(desired_q).distinct()

            # Then exclude groups that have any unwanted types
            if unwanted_types:
                queryset_with_desired = queryset_with_desired.exclude(unwanted_q)

            return queryset_with_desired.distinct()

        # For non-exclusive mode, just filter by desired types using Q objects
        desired_q = Q()
        for spatial_type in spatial_types:
            desired_q |= Q(features__feature_geometry__type=spatial_type)

        return queryset.filter(desired_q).distinct()


class SpatialFeatureGroupStaticManager(
    CommonTenantManager, models.Manager.from_queryset(SpatialFeatureGroupStaticQuerySet)
):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureGroupStatic(TenantModelMixin, UUIDModel, TimestampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    features = models.ManyToManyField(
        to="SpatialFeature",
        related_name="groups_temp",
        related_query_name="group_temp",
        through="mapping.SpatialFeatureGroupStaticFeatures",
        through_fields=("spatial_feature_groupstatic", "spatial_feature"),
        blank=True,
    )
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)

    objects = SpatialFeatureGroupStaticManager()
    tenant_id = "das_tenant_id"

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        verbose_name = "Feature Group"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


class DisplayCategoryManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class DisplayCategory(TenantModelMixin, TimestampedModel):
    """
    If the clients wish to group layers in a control or for ease of administration
    Boundaries, Water, Security etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = DisplayCategoryManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "Display Category"
        verbose_name_plural = "Display Categories"
        base_manager_name = "objects"
        default_manager_name = "objects"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "name"])]

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


class SpatialFeatureTypeTag(TenantModelMixin, TagModel):
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    name = models.CharField(unique=False, max_length=tagulous.settings.NAME_MAX_LENGTH)

    class TagMeta:
        pass

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            ),
            UniqueConstraint(fields=["das_tenant", "slug"], name="%(app_label)s_%(class)s_unique_slug_across_tenants"),
        ]
        indexes = [
            Index(fields=["das_tenant", "name"]),
            Index(fields=["das_tenant", "slug"]),
        ]


class TagField(TagulousTagField):
    forbidden_fields = ("db_table", "symmetrical")


class SpatialFeatureTypeManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureType(TenantModelMixin, TimestampedModel):
    # Note: referred as "Feature Class" on external APIs.

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    # JSON field for storing the json schema for each unique feature type
    attribute_schema = models.JSONField(default=dict, blank=True)
    # Tags will allow categorization according to different views (e.g., HF)
    tags = TagField(to=SpatialFeatureTypeTag, blank=True, through="mapping.SpatialFeatureTypeTags")
    # presentation fields
    # Boundaries, Water, Security etc.
    display_category = TenantForeignKey(to="DisplayCategory", on_delete=models.PROTECT, blank=True, null=True)
    # JSON Field for defining the basic presentation of the feature
    presentation = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    external_source = models.CharField(max_length=100, blank=True)
    is_visible = models.BooleanField(_("visible"), default=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = SpatialFeatureTypeManager()
    tenant_id = "das_tenant_id"
    # Points: https://www.mapbox.com/mapbox-gl-style-spec/#layers-symbol
    # Lines: https://www.mapbox.com/mapbox-gl-style-spec/#layers-line
    # Polygons: https://www.mapbox.com/mapbox-gl-style-spec/#layers-fill

    class Meta:
        verbose_name = "Feature Class"
        verbose_name_plural = "Feature Classes"
        base_manager_name = "objects"
        default_manager_name = "objects"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            ),
            UniqueConstraint(
                fields=["das_tenant", "external_id"], name="%(app_label)s_%(class)s_unique_external_id_across_tenants"
            ),
        ]
        indexes = [Index(fields=["das_tenant", "name"])]

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        return {}

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)

    @property
    def feature_count(self):
        return SpatialFeature.objects.filter(feature_type=self).count()

    def save(self, *args, **kwargs):
        try:
            if self.presentation.get("fill-opacity"):
                self.presentation["fill-opacity"] = float(self.presentation.get("fill-opacity"))
            if self.presentation.get("stroke-opacity"):
                self.presentation["stroke-opacity"] = float(self.presentation.get("stroke-opacity"))
        except ValueError as exc:
            logger.warning(exc)

        super(SpatialFeatureType, self).save(*args, **kwargs)
        self._bump_cache_version()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self._bump_cache_version()
        return result

    def _bump_cache_version(self):
        """Increment the vector tile cache version to invalidate cached tiles."""
        bump_vector_tile_data_version()


class SpatialFeatureTypeTags(TenantModelMixin, UUIDModel):
    spatialfeaturetype = TenantForeignKey(
        default=uuid.uuid4, on_delete=models.CASCADE, related_name="spatialfeaturetype", to="mapping.SpatialFeatureType"
    )
    spatialfeaturetypetag = TenantForeignKey(
        default=uuid.uuid4,
        on_delete=models.CASCADE,
        related_name="spatialfeaturetypetag",
        to="mapping.SpatialFeatureTypeTag",
    )
    das_tenant = models.ForeignKey(
        DASTenant,
        on_delete=models.CASCADE,
        default=default_tenant_id,
        related_name="%(app_label)s_%(class)s",
    )

    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()


class SpatialFeatureFile(SpatialFilesBase):
    """
    Special Feature loaded from uploaded shapefile
    INFO TenantModelMixin covered by abstract class
    """

    file_type = models.CharField(max_length=100, default="shapefile", choices=FILE_TYPES)
    feature_type = TenantForeignKey(to=SpatialFeatureType, on_delete=models.PROTECT, blank=True, null=True)
    feature_types_file = models.FileField(upload_to=upload_to, blank=True, null=True)

    class Meta:
        verbose_name = "Feature Import File"


class SpatialFeatureManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def create_spatialfeature(self, **values):
        return self.create(**values)


class SpatialFeature(TenantModelMixin, RevisionMixin, TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...

    GeoFeature is a PostGIS type that can accept the gamut of spatial types and provides
        better distance calculations when data spans large distances as opposed to a cartesian representation.
    Attributes:
        short_name: A shorter name used for cartographic display
        external_id: for ste, this is the ste_guid
        attributes: Status: Open/Closed/Seasonal/Unknown) <Roads Only>
            SpeedLimit <Roads Only>
            FenceHeight <Fenclines only>
            Status: Permanent/Temporary & Abandoned/Occupied <Human Settlement - Boma>
            Status: Active/Inactive <Airstrips>
            Seasonal Status: Permanent/Seasonal <Water & Rivers>
            Accessibility: Human/Livestock/Wildlife <Water>
            Notes
        provenance: where did the data come from? method?
            collect_user # who collected the data?
            collect_method # the method used to collect the data (e.g., GPS, Satellite, etc.)
            collect_date # when was the data collected?
            ground_verified # has the spatial feature been checked on the ground?
            spatial_feature_owners # The person/entity who owns the given spatial feature. E.g., 'Government of Kenya'
            spatial_data_owners = # The person/entity/organization who owns the GIS data
            created_user # who created the feature in the STESpatial database
            created_date # when was the feature created in the STESpatial database
            last_edited_user # who last edited the feature in the STESpatial database
            last_edited_date # when was the feature last edited in the STESpatial database
            other_id # this will map from the other_id' column in STESpatial

    """

    revision_ignore_fields = ("updated_at",)
    id = models.UUIDField(primary_key=True, unique=True, default=uuid.uuid4)
    feature_type = TenantForeignKey(SpatialFeatureType, on_delete=models.PROTECT)
    name = models.CharField(max_length=255, blank=True)
    # A shorter name used for cartographic display
    short_name = models.CharField(max_length=25, blank=True)
    # for ste, this is the ste_guid
    external_id = models.CharField(max_length=255, blank=True, null=True)
    external_source = models.CharField(max_length=100, blank=True)
    description = models.TextField(null=True, blank=True)
    presentation = models.JSONField(default=dict, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    feature_geometry = models.GeometryField(geography=True, srid=4326)
    feature_geometry_webmercator = models.GeometryField(
        srid=3857,
        null=True,
        blank=True,
        help_text="Simplified Web Mercator geometry for vector tile serving (2.5m tolerance)",
    )
    spatialfile = TenantForeignKey(to=SpatialFeatureFile, null=True, blank=True, on_delete=models.SET_NULL)
    arcgis_item = TenantForeignKey(to="ArcgisItem", null=True, blank=True, on_delete=models.CASCADE)
    revision = Revision()
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    objects = SpatialFeatureManager()
    tenant_id = "das_tenant_id"

    class Meta:
        verbose_name = "Feature"
        ordering = ["name"]
        base_manager_name = "objects"
        default_manager_name = "objects"

    def _bump_cache_version(self):
        """Increment the vector tile cache version to invalidate cached tiles."""
        bump_vector_tile_data_version()

    def _generate_webmercator_geometry(self):
        """Generate simplified Web Mercator geometry from the source geometry."""
        if not self.feature_geometry:
            return None

        try:
            # Transform to Web Mercator
            webmerc_geom = self.feature_geometry.transform(3857, clone=True)

            # Apply 2.5m simplification tolerance - good balance of performance and detail
            # Preserves details visible at zoom 16+ while removing micro-features
            simplified = webmerc_geom.simplify(tolerance=2.5, preserve_topology=True)

            return simplified
        except Exception as e:
            logger.warning(f"Failed to generate Web Mercator geometry for SpatialFeature {self.id}: {e}")
            return None

    def save(self, *args, **kwargs):
        # Generate optimized Web Mercator geometry on save
        if self.feature_geometry:
            self.feature_geometry_webmercator = self._generate_webmercator_geometry()

        result = super().save(*args, **kwargs)
        self._bump_cache_version()
        return result

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self._bump_cache_version()
        return result

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        if self.feature_type.presentation:
            return self.feature_type.presentation
        return {}

    def clean(self):
        if self.feature_geometry.geom_type == "Point":
            self.feature_geometry = geos.MultiPoint(geos.GEOSGeometry(self.feature_geometry.ewkb))
        elif self.feature_geometry.geom_type == "LineString":
            self.feature_geometry = geos.MultiLineString(
                [
                    geos.GEOSGeometry(self.feature_geometry.ewkb),
                ]
            )
        elif self.feature_geometry.geom_type == "Polygon":
            self.feature_geometry = geos.MultiPolygon(
                [
                    geos.GEOSGeometry(self.feature_geometry.ewkb),
                ]
            )
        else:
            logger.debug(f"Not converting type {type(self.feature_geometry)}")

    def __str__(self):
        return "{0}-{1}-{2}".format(self.name, self.feature_type.name, self.id)


class ArcgisGroupManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


class ArcgisGroup(TenantModelMixin, TimestampedModel, UUIDModel):
    name = models.CharField(max_length=100, blank=True, null=True)
    group_id = models.CharField(max_length=100, blank=False)
    config_id = models.CharField(max_length=100, blank=False)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = ArcgisGroupManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    def __str__(self):
        return self.name


class ArcgisConfiguration(TenantModelMixin, TimestampedModel, UUIDModel):
    disable_import_feature_class_presentation = models.BooleanField(default=False)
    service_url = models.CharField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="Leave blank to connect to ArcGIS Online, " "or enter your ArcGIS Enterprise service URL",
    )
    config_name = models.CharField(max_length=100, blank=False, verbose_name="Configuration name")
    search_text = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Search text",
        help_text="Leave blank to get groups within your ArcGIS org\n"
        "or enter text for groups to search for outside your ArdGIS org",
    )
    # todo: the FK should be on the other end of the relationship, i.e., in ArcgisConfiguration
    groups = TenantForeignKey(ArcgisGroup, blank=True, on_delete=models.SET_NULL, null=True)
    username = models.CharField(max_length=100, blank=False, help_text="ArcGIS account username")
    password = models.CharField(max_length=100, blank=False)
    source = models.CharField(max_length=100, blank=True, null=True, default="ArcGis")
    name_field = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="Name",
        help_text="Name of field in your GIS data that has the feature name. Default is Name",
    )
    id_field = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="GlobalID",
        help_text="Name of field in your GIS data that has the feature ID. Default is GlobalID",
    )
    type_label = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Type field",
        default="FeatureType",
        help_text="Name of field in your GIS data that has the feature type. Defaults are type and FeatureType",
    )
    last_download = models.DateTimeField(blank=True, null=True, verbose_name="Last Download Time")
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = CommonTenantManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        verbose_name = "Feature Service Configuration"
        constraints = [
            UniqueConstraint(
                fields=["das_tenant", "config_name"],
                name="%(app_label)s_%(class)s_unique_name_across_tenants",
            )
        ]
        indexes = [Index(fields=["das_tenant", "config_name"])]

    def __str__(self):
        return self.config_name

    @property
    def last_download_time(self):
        t_zone = timezone(settings.TIME_ZONE)
        fmt = "%d %b %Y, %H:%M %p (%Z)"
        return self.last_download.astimezone(t_zone).strftime(fmt)


class ArcgisItemManager(TenantManagerMixin, models.Manager):
    use_in_migrations = True

    def get_by_natural_key(self, name):
        return self.get(name=name)


# Minimal model for an arcgis.gis.Item
class ArcgisItem(TenantModelMixin, TimestampedModel):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=50)
    arcgis_config = TenantForeignKey(to=ArcgisConfiguration, on_delete=models.SET_NULL, null=True)
    das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, default=default_tenant_id)
    tenant_id = "das_tenant_id"
    objects = ArcgisItemManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"

    @property
    def features(self):
        return SpatialFeature.objects.filter(arcgis_item=self)
