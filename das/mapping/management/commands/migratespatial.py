import logging
from enum import Enum

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError

from mapping import models

logger = logging.getLogger(__name__)


class MigrateType(Enum):
    ErrorOnExisting = 1  # Throw error if existing records found
    AppendNew = 2  # ignore existing, append new
    OverWrite = 3  # overwrite existing, append new


class ExistingFeatures(Exception):
    pass


class Command(BaseCommand):
    help = 'Migrate point/line/polygon to spatialfeature'
    migrate_type = MigrateType.ErrorOnExisting
    create_fn = 'create'
    num_fs = 0
    num_ft = 0
    num_f = 0

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('-o', '--overwrite', action='store_true',
                           help='Overwrite any existing features', )
        group.add_argument('-a', '--append', action='store_true',
                           help='Append new features, do not update existing', )

    def handle(self, *args, **options):
        self.num_fs, self.num_ft, self.num_f = 0, 0, 0
        self.migrate_type = MigrateType.OverWrite if options[
            'overwrite'] else MigrateType.AppendNew if options['append'] else MigrateType.ErrorOnExisting

        if self.migrate_type == MigrateType.OverWrite:
            self.create_fn = 'update_or_create'

        with transaction.atomic():
            self.migrate_featuresets()
            self.migrate_featuretypes()
            self.migrate_features()

        self.stdout.write('FeatureSets migrated: %d, FeatureTypes migrated: %d, Features migrated: %d' %
                          (self.num_fs, self.num_ft, self.num_f))

    def migrate_featuresets(self):
        logger.debug('Migrating FeatureSets')

        for f in models.FeatureSet.objects.all():
            values = dict(name=f.name)
            try:
                with transaction.atomic():
                    func = getattr(models.DisplayCategory.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_fs += 1
            except IntegrityError:
                if MigrateType.ErrorOnExisting == self.migrate_type:
                    raise ExistingFeatures(
                        f'DisplayCategory already exists {f.name}')

    def migrate_featuretypes(self):
        logger.debug('Migrating FeatureTypes')
        for f in models.FeatureType.objects.all():
            featuresets = models.FeatureSet.objects.filter(types__id=f.id)
            for featureset in featuresets:
                dc = models.DisplayCategory.objects.get(id=featureset.id)
                values = dict(name=f.name,
                              presentation=f.presentation,
                              display_category=dc,
                              )

                try:
                    func = getattr(models.SpatialFeatureType.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_ft += 1
                except IntegrityError:
                    if MigrateType.ErrorOnExisting == self.migrate_type:
                        raise ExistingFeatures(
                            f'SpatialFeatureType already exists {f.name}')

    def migrate_features(self):
        logger.debug('Migrating Point, Line and Polygon features')

        for feature_class in (models.PointFeature, models.LineFeature, models.PolygonFeature):
            for f in feature_class.objects.all():
                sft = models.SpatialFeatureType.objects.get(id=f.type.id)
                values = dict(name=f.name,
                              feature_geometry=f.feature_geometry,
                              provenance=f.fields,
                              external_id=f.external_id,
                              feature_type=sft
                              )
                try:
                    func = getattr(models.SpatialFeature.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_f += 1
                except IntegrityError:
                    if MigrateType.ErrorOnExisting == self.migrate_type:
                        raise ExistingFeatures(
                            f'{feature_class} already exists {f.name}')
