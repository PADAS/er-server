import datetime
import glob
import logging
import os
import uuid

from model_utils.managers import InheritanceManager
from pytz import timezone
from tagulous.models import TagField, TagModel

from django.conf import settings
from django.contrib.gis import geos
from django.contrib.gis.db import models
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.storage import FileSystemStorage
from django.urls import NoReverseMatch, reverse
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from core.models import TimestampedModel
from mapping.app_settings import MBTILES
from mapping.mbtiles import (ExtractionError, GoogleProjection,
                             InvalidFormatError, MBTilesReader)
from mapping.utils import SPATIAL_FILES_FOLDER, check_file_extension
from revision.manager import Revision, RevisionMixin
from utils.decorator import reify

logger = logging.getLogger(__name__)

FILE_TYPES = (
    ('shapefile', 'Shapefile'),
    # Commenting out geodatabase for now, until we can verify functionality with a .gdb file.
    # ('geodatabase', 'Geodatabase'),
    ('geojson', 'GeoJSON'),
)


class Map(TimestampedModel):
    """
    A Map defines the center location, zoom level
    """
    class Meta:
        verbose_name = 'Map Quicklink'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    attributes = models.JSONField(default=dict, blank=True)
    center = models.PointField(srid=4326)
    zoom = models.IntegerField()

    def __str__(self):
        return self.name


class TileLayerQuerySet(models.QuerySet):
    def by_ordernum(self):
        return self.order_by('ordernum', 'name')


class TileLayer(TimestampedModel):
    """
    External
    """
    class Meta:
        verbose_name = 'Basemap'
        ordering = ['name']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    attributes = models.JSONField(default=dict, blank=True)
    ordernum = models.SmallIntegerField(blank=True, null=True)

    objects = TileLayerQuerySet.as_manager()

    def __str__(self):
        return self.name


class FeatureTypeManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class FeatureType(TimestampedModel):
    """
    If the clients wish to group layers in a control or for ease of administration

    MapBox convention for stylization of feature types:
    Points: https://www.mapbox.com/mapbox-gl-style-spec/#layers-symbol
    Lines: https://www.mapbox.com/mapbox-gl-style-spec/#layers-line
    Polygons: https://www.mapbox.com/mapbox-gl-style-spec/#layers-fill
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    presentation = models.JSONField(default=dict, blank=True)
    objects = FeatureTypeManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)

    @property
    def feature_count(self):
        return PolygonFeature.objects.filter(type=self).count() + \
            LineFeature.objects.filter(type=self).count() + \
            PointFeature.objects.filter(type=self).count()


class FeatureSetManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class FeatureSet(TimestampedModel):
    """
    A grouping of features that should be toggled together on the map,
      e.g. a set of camps or a system of rivers
      ... better than handling as a layer group in UI as it allows grouping to be controlled in db?
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    types = models.ManyToManyField(to=FeatureType, related_name='featuresets')

    description = models.TextField(null=True, blank=True)

    objects = FeatureSetManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


@deconstructible
class TempStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        import tempfile

        temp_directory_name = tempfile.mkdtemp()
        kwargs.update({'location': temp_directory_name, })
        super(TempStorage, self).__init__(**kwargs)


def upload_to(instance, filename):
    '''
    Providing a path to an Spatialfiles.
    :param instance: SpatialFile of SpatialFeatureFile instance
    :param filename: default filename.
    :return: relative path for storing uploaded file
    '''
    filename = filename.split('/')[-1]
    timestamp = "{:%Y%m%d%H%s}".format(datetime.datetime.now())
    file_path = f'{SPATIAL_FILES_FOLDER}/{timestamp}-{filename}'
    return file_path


class SpatialFilesBase(TimestampedModel):
    """
    Base model for uploading Spatial files such as shapefile
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, blank=True,
                            verbose_name='SpatialFile Name')
    description = models.CharField(max_length=100, blank=True)
    data = models.FileField(upload_to=upload_to, blank=False)
    layer_number = models.IntegerField(blank=True, null=True, default=0)
    name_field = models.CharField(max_length=100, blank=True, null=True)
    id_field = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(
        max_length=1000, blank=True, null=True, verbose_name='Feature Load Status')

    class Meta:
        abstract = True

    # Clean method is used for better error handling within the admin form
    # itself. To have the file data available, save method needs to be invoked.
    #  Cleanup method will remove files in case of validation error.
    # Can a better way be utilized which avoids saving the Spatial file model?

    def clean(self):
        """
        Overwriting clean method to have error handling within the admin form.
        """
        if not self.data:
            raise ValidationError({'data': []})

        feature_types_file = getattr(self, 'feature_types_file', None)
        file_type = getattr(self, 'file_type', None)

        if file_type:
            check_file_extension(self.file_type, self.data, feature_types_file)

    def __str__(self):
        return str(self.id)


class SpatialFile(SpatialFilesBase):
    """
    Geometry type [polygon, line, point] loaded from uploaded shapefile
    """
    feature_set = models.ForeignKey(to=FeatureSet, on_delete=models.PROTECT)
    feature_type = models.ForeignKey(to=FeatureType, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Spatial File'


class Feature(TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)
    type = models.ForeignKey(to=FeatureType, on_delete=models.PROTECT)

    description = models.TextField(null=True, blank=True)

    # attributes for presentation
    presentation = models.JSONField(default=dict, blank=True)
    fields = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)

    # the feature set with which this feature is being grouped.
    # todo:  evaluate whether many-to-many might be a better approach or stick
    # with this simple approach
    # probably should be spelled feature_set
    featureset = models.ForeignKey(
        to=FeatureSet, null=True, on_delete=models.PROTECT)

    spatialfile = models.ForeignKey(
        to=SpatialFile, null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        if self.type.presentation:
            return self.type.presentation
        return {}

    class Meta:
        abstract = True
        ordering = ['name']

    # todo:  perhaps type and name?
    def __str__(self):
        return u"{0}".format(self.name)


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
        super(ImproperlyConfigured, self).__init__(
            _("MBTILES['root'] '%s' does not exist") % MBTILES['root'])


class MBTilesManager(object):
    """ List available MBTiles in MBTILES['root']
        source: https://github.com/makinacorpus/django-mbtiles.git
        license: Lesser GNU Public License
    """

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not os.path.exists(MBTILES['root']):
            self.logger.error('MBTILES folder not set %s',
                              MBTilesFolderError())
        self.folder = MBTILES['root']

    def filter(self, catalog=None):
        if catalog:
            self.folder = self.catalog_path(catalog)
        return self

    def all(self):
        return self

    def __iter__(self):
        filepattern = os.path.join(self.folder, '*.%s' % MBTILES['ext'])
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
        for dirname, dirnames, filenames in os.walk(MBTILES['root']):
            return dirnames
        return []

    def default_catalog(self):
        if len(list(self)) == 0 and len(self._subfolders) > 0:
            return self._subfolders[0]
        return None

    def catalog_path(self, catalog=None):
        if catalog is None:
            return MBTILES['root']
        path = os.path.join(MBTILES['root'], catalog)
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

        mbtiles_file = "%s.%s" % (mbtiles_file, MBTILES['ext'])
        if os.path.exists(mbtiles_file):
            return mbtiles_file

        raise MBTilesNotFoundError(
            _("'%s' not found in %s") % (mbtiles_file, basepath))


class MBTiles(object):
    """ Represent a MBTiles file """

    objects = MBTilesManager()

    def __init__(self, name, catalog=None):
        self.catalog = catalog
        self.fullpath = self.objects.fullpath(name, catalog)
        self.basename = os.path.basename(self.fullpath)
        self._reader = MBTilesReader(
            self.fullpath, tilesize=MBTILES['tile_size'])

    @property
    def id(self):
        iD, ext = os.path.splitext(self.basename)
        return iD

    @property
    def name(self):
        return self.metadata.get('name', self.id)

    @property
    def filesize(self):
        return os.path.getsize(self.fullpath)

    @reify
    def metadata(self):
        return self._reader.metadata()

    @reify
    def bounds(self):
        bounds = self.metadata.get('bounds', '').split(',')
        if len(bounds) != 4:
            logger.warning(
                _("Invalid bounds metadata in '%s', fallback to whole world.") % self.name)
            bounds = [-180, -90, 180, 90]
        return tuple(map(float, bounds))

    @reify
    def center(self):
        """
        Return the center (x,y) of the map at this zoom level.
        """
        center = self.metadata.get('center', '').split(',')
        if len(center) == 3:
            lon, lat, zoom = map(float, center)
            zoom = int(zoom)
            if zoom not in self.zoomlevels:
                logger.warning(_("Invalid zoom level (%s), fallback to middle zoom (%s)") % (
                    zoom, self.middlezoom))
                zoom = self.middlezoom
            return (lon, lat, zoom)
        # Invalid center from metadata, guess center from bounds
        lat = self.bounds[1] + (self.bounds[3] - self.bounds[1]) / 2
        lon = self.bounds[0] + (self.bounds[2] - self.bounds[0]) / 2
        return (lon, lat, self.middlezoom)

    @property
    def minzoom(self):
        z = self.metadata.get('minzoom', self.zoomlevels[0])
        return int(z)

    @property
    def maxzoom(self):
        z = self.metadata.get('maxzoom', self.zoomlevels[-1])
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
        proj = GoogleProjection(MBTILES['tile_size'], [zoom])
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
        jsonp.update(**{
            "bounds": self.bounds,
            "center": self.center,
            "minzoom": self.minzoom,
            "maxzoom": self.maxzoom,
            "autoscale": False,
        })
        # Additionnal info
        try:
            kwargs = dict(name=self.id, x='{x}', y='{y}', z='{z}')
            if self.catalog:
                kwargs['catalog'] = self.catalog
            tilepattern = reverse("mapping:tile", kwargs=kwargs)
            gridpattern = reverse("mapping:grid", kwargs=kwargs)
        except NoReverseMatch:
            # In case django-mbtiles was not registered in namespace mbtilesmap
            tilepattern = reverse("tile", kwargs=dict(
                name=self.id, x='{x}', y='{y}', z='{z}'))
            gridpattern = reverse("grid", kwargs=dict(
                name=self.id, x='{x}', y='{y}', z='{z}'))
        tilepattern = request.build_absolute_uri(tilepattern)
        gridpattern = request.build_absolute_uri(gridpattern)
        tilepattern = tilepattern.replace('%7B', '{').replace('%7D', '}')
        gridpattern = gridpattern.replace('%7B', '{').replace('%7D', '}')
        jsonp.update(**{
            "tilejson": "2.1.0",
            "id": self.id,
            "name": self.name,
            "scheme": "xyz",
            "basename": self.basename,
            "filesize": self.filesize,
            "tiles": [tilepattern],
            "grids": [gridpattern]
        })
        return jsonp


"""Below are new classes proposed by Jake for structuring spatial data in DAS"""


class SpatialFeatureGroupManager(InheritanceManager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureGroup(TimestampedModel):
    """
    A grouping of features that should be toggled together on the map,
      e.g. a set of camps or a system of rivers
      ... better than handling as a layer group in UI as it allows grouping
       to be controlled in db?
    """
    class Meta:
        verbose_name = 'Base Feature Group'
        ordering = ['name']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    objects = SpatialFeatureGroupManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


class SpatialFeatureGroupQuery(SpatialFeatureGroup):
    class Meta:
        verbose_name = 'Calculated Feature Group'


class SpatialFeatureGroupStatic(SpatialFeatureGroup):
    """Static group of features
    """
    class Meta:
        verbose_name = 'Feature Group'

    features = models.ManyToManyField(to='SpatialFeature', related_name='groups', related_query_name='group',
                                      blank=True,)


class DisplayCategoryManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class DisplayCategory(TimestampedModel):
    """
    If the clients wish to group layers in a control or for ease of administration
    Boundaries, Water, Security etc.
    """
    class Meta:
        verbose_name = 'Display Category'
        verbose_name_plural = 'Display Categories'
        ordering = ['name']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)

    objects = DisplayCategoryManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


class SpatialFeatureTypeTag(TagModel):
    class TagMeta:
        pass


class SpatialFeatureTypeManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureType(TimestampedModel):
    class Meta:
        verbose_name = 'Feature Class'
        verbose_name_plural = 'Feature Classes'
        ordering = ['name']

    objects = SpatialFeatureTypeManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, unique=True)
    # JSON field for storing the json schema for each unique feature type
    attribute_schema = models.JSONField(default=dict, blank=True)
    # Tags will allow categorization according to different views (e.g., HF)
    tags = TagField(to=SpatialFeatureTypeTag, blank=True)

    # presentation fields
    # Boundaries, Water, Security etc.
    display_category = models.ForeignKey(
        to='DisplayCategory', on_delete=models.PROTECT, blank=True, null=True)
    # JSON Field for defining the basic presentation of the feature
    presentation = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=255, unique=True, blank=True,
                                   null=True)
    external_source = models.CharField(max_length=100, blank=True)
    is_visible = models.BooleanField(_('visible'), default=True)

    # Points: https://www.mapbox.com/mapbox-gl-style-spec/#layers-symbol
    # Lines: https://www.mapbox.com/mapbox-gl-style-spec/#layers-line
    # Polygons: https://www.mapbox.com/mapbox-gl-style-spec/#layers-fill

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        return {}

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name

    @property
    def feature_count(self):
        return SpatialFeature.objects.filter(feature_type=self).count()

    def save(self, *args, **kwargs):
        try:
            if self.presentation.get('fill-opacity'):
                self.presentation['fill-opacity'] = float(
                    self.presentation.get('fill-opacity'))
            if self.presentation.get('stroke-opacity'):
                self.presentation['stroke-opacity'] = float(
                    self.presentation.get('stroke-opacity'))
        except ValueError as exc:
            logger.warning(exc)
        finally:
            super(SpatialFeatureType, self).save(*args, **kwargs)


class SpatialFeatureFile(SpatialFilesBase):
    """
    Special Feature loaded from uploaded shapefile
    """
    file_type = models.CharField(
        max_length=100, default='shapefile', choices=FILE_TYPES)
    feature_type = models.ForeignKey(
        to=SpatialFeatureType, on_delete=models.PROTECT, blank=True, null=True)
    feature_types_file = models.FileField(
        upload_to=upload_to, blank=True, null=True)

    class Meta:
        verbose_name = 'Feature Import File'


class SpatialFeatureManager(models.Manager):
    def create_spatialfeature(self, **values):
        return self.create(**values)


class SpatialFeature(RevisionMixin, TimestampedModel):
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
    class Meta:
        verbose_name = 'Feature'
        ordering = ['name']

    objects = SpatialFeatureManager()
    revision_ignore_fields = ('updated_at', )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    feature_type = models.ForeignKey(
        SpatialFeatureType, on_delete=models.PROTECT)
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
    spatialfile = models.ForeignKey(
        to=SpatialFeatureFile, null=True, blank=True, on_delete=models.SET_NULL)
    arcgis_item = models.ForeignKey(
        to='ArcgisItem', null=True, blank=True, on_delete=models.CASCADE)
    revision = Revision()

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        if self.feature_type.presentation:
            return self.feature_type.presentation
        return {}

    def clean(self):
        if self.feature_geometry.geom_type == 'Point':
            self.feature_geometry = geos.MultiPoint(
                geos.GEOSGeometry(self.feature_geometry.ewkb))
        elif self.feature_geometry.geom_type == 'LineString':
            self.feature_geometry = geos.MultiLineString(
                [geos.GEOSGeometry(self.feature_geometry.ewkb), ])
        elif self.feature_geometry.geom_type == 'Polygon':
            self.feature_geometry = geos.MultiPolygon(
                [geos.GEOSGeometry(self.feature_geometry.ewkb), ])
        else:
            logger.debug(f'Not converting type {type(self.feature_geometry)}')

    def __str__(self):
        return '{0}-{1}-{2}'.format(self.name, self.feature_type.name, self.id)


class ArcgisGroup(TimestampedModel):
    name = models.CharField(max_length=100, blank=True, null=True)
    group_id = models.CharField(max_length=100, blank=False)
    # todo: this should be the FK
    config_id = models.CharField(max_length=100, blank=False)

    def __str__(self):
        return self.name


class ArcgisConfiguration(TimestampedModel):
    disable_import_feature_class_presentation = models.BooleanField(
        default=False)
    service_url = models.CharField(max_length=2000, blank=True, null=True,
                                   help_text='Leave blank to connect to ArcGIS Online, '
                                             'or enter your ArcGIS Enterprise service URL')
    config_name = models.CharField(
        max_length=100, blank=False, unique=True, verbose_name='Configuration name')
    search_text = models.CharField(max_length=100, blank=True, verbose_name='Search text',
                                   help_text='Leave blank to get groups within your ArcGIS org\n'
                                             'or enter text for groups to search for outside your ArdGIS org')
    # todo: the FK should be on the other end of the relationship, i.e., in ArcgisConfiguration
    groups = models.ForeignKey(
        ArcgisGroup, blank=True, on_delete=models.SET_NULL, null=True)
    username = models.CharField(
        max_length=100, blank=False, help_text='ArcGIS account username')
    password = models.CharField(max_length=100, blank=False)
    source = models.CharField(
        max_length=100, blank=True, null=True, default='ArcGis')
    name_field = models.CharField(max_length=100, blank=True, null=True, default='Name',
                                  help_text='Name of field in your GIS data that has the feature name. Default is Name')
    id_field = models.CharField(max_length=100, blank=True, null=True, default='GlobalID',
                                help_text='Name of field in your GIS data that has the feature ID. Default is GlobalID')
    type_label = models.CharField(max_length=100, blank=True, null=True, verbose_name='Type field', default='FeatureType',
                                  help_text='Name of field in your GIS data that has the feature type. Defaults are type and FeatureType')
    last_download = models.DateTimeField(
        blank=True, null=True, verbose_name='Last Download Time')

    class Meta:
        verbose_name = 'Feature Service Configuration'

    @property
    def last_download_time(self):
        t_zone = timezone(settings.TIME_ZONE)
        fmt = '%d %b %Y, %H:%M %p (%Z)'
        return self.last_download.astimezone(t_zone).strftime(fmt)

    def __str__(self):
        return self.config_name


# Minimal model for an arcgis.gis.Item
class ArcgisItem(TimestampedModel):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=50)
    arcgis_config = models.ForeignKey(
        to=ArcgisConfiguration, on_delete=models.SET_NULL, null=True)

    @property
    def features(self):
        return SpatialFeature.objects.filter(arcgis_item=self)
