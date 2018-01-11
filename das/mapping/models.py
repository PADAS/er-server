import uuid
import os
import logging
import glob

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse, NoReverseMatch
from django.utils.translation import ugettext_lazy as _
from tagulous.models import TagField, TagModel
from model_utils.managers import InheritanceManager

from core.models import TimestampedModel
from utils.decorator import reify
from mapping.app_settings import MBTILES
from mapping.mbtiles import ExtractionError, GoogleProjection, MBTilesReader
from mapping.mbtiles import InvalidFormatError
from revision.manager import Revision, RevisionMixin


logger = logging.getLogger(__name__)


class Map(TimestampedModel):
    """
    A Map defines the center location, zoom level and tile layers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    attributes = JSONField()
    center = models.PointField(srid=4326)
    zoom = models.IntegerField()

    def __str__(self):
        return self.name


TILE_TYPES = (
    ('mbtiles', 'Local MBTiles'),
    ('external', 'External Tile Server'),
)


class TileLayer(TimestampedModel):
    """
    External or MBTiles
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    attributes = JSONField()
    version = models.CharField(max_length=80, default='1.0.0')
    tile_type = models.CharField(max_length=20,
                                 choices=TILE_TYPES, default='mbtiles')
    maps = models.ManyToManyField(Map)

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
    name = models.CharField(max_length=80, unique=True)
    presentation = JSONField(default=dict)
    objects = FeatureTypeManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


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
    name = models.CharField(max_length=80, unique=True)
    types = models.ManyToManyField(to=FeatureType, related_name='featuresets')

    description = models.TextField(null=True, blank=True)

    objects = FeatureSetManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


class Feature(TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80)
    type = models.ForeignKey(to=FeatureType, on_delete=models.PROTECT)

    description = models.TextField(null=True, blank=True)

    # attributes for presentation
    presentation = JSONField(default=dict)
    fields = JSONField(default=dict)
    external_id = models.CharField(max_length=80, blank=True, null=True)

    # the feature set with which this feature is being grouped.
    # todo:  evaluate whether many-to-many might be a better approach or stick
    # with this simple approach
    # probably should be spelled feature_set
    featureset = models.ForeignKey(to=FeatureSet, null=True, on_delete=models.PROTECT)

    @property
    def default_presentation(self):
        if self.presentation:
            return self.presentation
        if self.type.presentation:
            return self.type.presentation
        return {}

    class Meta:
        abstract = True

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


class DisplayCategoryManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class DisplayCategory(models.Model):
    """
    If the clients wish to group layers in a control or for ease of administration
    Boundaries, Water, Security etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)

    objects = DisplayCategoryManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


class SpatialFeatureGroupManager(InheritanceManager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureGroup(models.Model):
    """
    A grouping of features that should be toggled together on the map,
      e.g. a set of camps or a system of rivers
      ... better than handling as a layer group in UI as it allows grouping
       to be controlled in db?
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    objects = SpatialFeatureGroupManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name


class SpatialFeatureGroupQuery(SpatialFeatureGroup):
    pass


class SpatialFeatureGroupStatic(SpatialFeatureGroup):
    """Static group of features
    """
    features = models.ManyToManyField(to='SpatialFeature', related_name='groups',
                                      blank=True)


class SpatialFeatureTypeTag(TagModel):
    class TagMeta:
        pass


class SpatialFeatureTypeManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class SpatialFeatureType(models.Model):
    objects = SpatialFeatureTypeManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100)
    # JSON field for storing the json schema for each unique feature type
    attribute_schema = JSONField(default=dict)
    tags = TagField(to=SpatialFeatureTypeTag)  # Tags will allow categorization according to different views (e.g., HF)

    # presentation fields
    # Boundaries, Water, Security etc.
    display_category = models.ForeignKey(to='DisplayCategory', on_delete=models.PROTECT)
    # JSON Field for defining the basic presentation of the feature
    presentation = JSONField(default=dict)
    provenance = JSONField(default=dict)
    external_id = models.CharField(max_length=100, unique=True, blank=True,
                                   null=True)
    external_source = models.CharField(max_length=25, blank=True)

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


class SpatialFeatureManager(models.Manager):
    def create_spatialfeature(self, **values):
        return self.create(**values)


class SpatialFeature(RevisionMixin, TimestampedModel):
    """
    A vector feature, e.g. a boundary, a hut, a village, a river ...

    GeoFeature is a PostGIS type that can accept the gamut of spatial types and provides
        better distance calculations when data spans large distances as opposed to a cartesian representation.

    """
    objects = SpatialFeatureManager()

    revision_ignore_fields = ('updated_at', )

    # data fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    feature_type = models.ForeignKey(SpatialFeatureType, on_delete=models.PROTECT)

    name = models.CharField(max_length=50, blank=True)
    # A shorter name used for cartographic display
    short_name = models.CharField(max_length=25, blank=True)
    # for ste, this is the ste_guid
    external_id = models.CharField(max_length=100, unique=True, blank=True,
                                   null=True)
    external_source = models.CharField(max_length=25, blank=True)

    attributes = JSONField(default=dict)

    # Status: Open/Closed/Seasonal/Unknown) <Roads Only>
    # SpeedLimit <Roads Only>
    # FenceHeight <Fenclines only>
    # Status: Permanent/Temporary & Abandoned/Occupied <Human Settlement - Boma>
    # Status: Active/Inactive <Airstrips>
    # Seasonal Status: Permanent/Seasonal <Water & Rivers>
    # Accessibility: Human/Livestock/Wildlife <Water>
    # Notes

    # where did the data come from? method?
    provenance = JSONField(default=dict)
    # collect_user # who collected the data?
    # collect_method # the method used to collect the data (e.g., GPS, Satellite, etc.)
    # collect_date # when was the data collected?
    # ground_verified # has the spatial feature been checked on the ground?
    # spatial_feature_owners # The person/entity who owns the given spatial feature. E.g., 'Government of Kenya'
    # spatial_data_owners = # The person/entity/organization who owns the GIS data
    # created_user # who created the feature in the STESpatial database
    # created_date # when was the feature created in the STESpatial database
    # last_edited_user # who last edited the feature in the STESpatial database
    # last_edited_date # when was the feature last edited in the STESpatial database
    # other_id # this will map from the other_id' column in STESpatial

    feature_geometry = models.GeometryField(geography=True, srid=4326)

    revision = Revision()

    def __str__(self):
        return '{0}-{1}-{2}'.format(self.feature_type.name, self.id, self.name)
