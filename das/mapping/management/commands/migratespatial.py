import logging
from collections import defaultdict
from enum import Enum
from itertools import chain
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
from django.conf import settings

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

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('-o', '--overwrite', action='store_true',
                           help='Overwrite any existing features', )
        group.add_argument('-a', '--append', action='store_true',
                           help='Append new features, do not update existing', )

    def handle(self, *args, **options):
        self.num_fs, self.num_ft, self.num_f, self.num_files = 0, 0, 0, 0
        self.migrate_type = MigrateType.OverWrite if options[
            'overwrite'] else MigrateType.AppendNew if options['append'] else MigrateType.ErrorOnExisting

        if self.migrate_type == MigrateType.OverWrite:
            self.create_fn = 'update_or_create'

        self.update_visible_flag = True
        if self.migrate_type == MigrateType.OverWrite or self.migrate_type == MigrateType.AppendNew:
            self.update_visible_flag = False

        featuresets_by_types = defaultdict(set)
        featuresets = set()

        # start from point/line/poly features
        all_features = list(chain(models.PointFeature.objects.all(),
                                  models.LineFeature.objects.all(),
                                  models.PolygonFeature.objects.all()))
        for feature in all_features:
            if feature.featureset: featuresets.add(feature.featureset)
            featuresets_by_types[feature.type].add(feature.featureset)

        # start from feature types: get featuretypes/sets not associated with features
        for ft in models.FeatureType.objects.all():
            qs = models.FeatureSet.objects.filter(types__id=ft.id)
            if qs:
                featuresets.update(qs)
                featuresets_by_types[ft].update(qs)
            else:
                featuresets_by_types[ft].add(None)

        # finally get any featuresets not associated to featuretypes
        fset_ids = [k.id for k in featuresets]
        remaining_fsets = models.FeatureSet.objects.exclude(id__in=fset_ids)
        featuresets.update(remaining_fsets)

        self.stdout.write('%s (UTC) migrating %s' % (datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S"), settings.UI_SITE_URL))

        with transaction.atomic():
            remapped_sfts = {}
            self.migrate_featuresets(featuresets)
            self.migrate_featuretypes(featuresets_by_types, remapped_sfts)
            self.migrate_features(all_features, remapped_sfts)
            self.migrate_spatialfiles()
            self.update_is_visible(featuresets_by_types.keys(), list(remapped_sfts.values()))

        self.stdout.write(
            'FeatureSets migrated: %d, FeatureTypes migrated: %d, Features migrated: %d, files migrated: %d' %
            (self.num_fs, self.num_ft, self.num_f, self.num_files))
        self.stdout.write('%s SPATIAL DATA MIGRATION COMPLETE' % datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S"))

    def migrate_featuresets(self, featuresets):
        self.stdout.write('Migrating FeatureSets')

        for f in featuresets:
            values = dict(name=f.name)
            try:
                with transaction.atomic():
                    func = getattr(models.DisplayCategory.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_fs += 1
            except IntegrityError:
                if MigrateType.ErrorOnExisting == self.migrate_type:
                    raise ExistingFeatures(f'DisplayCategory already exists {f.name}')

    def migrate_featuretypes(self, featuresets_by_types, remapped_sfts):
        self.stdout.write('Migrating FeatureTypes')
        for ftype, fsets in featuresets_by_types.items():
            if len(fsets) > 1:
                self.stdout.write(f'FeatureType {ftype} associated with multiple FeatureSets: {fsets}')
            afeatureset = fsets.pop()

            if not models.SpatialFeatureType.objects.filter(id=ftype.id).exists():
                self._create_spatial_feature_type(afeatureset, ftype.name, ftype.presentation, ftype.id)

                # breaking m2m: create a new spatial feature type to associate with the remaining featuresets
                for f in fsets:
                    remapped_sft_key = (f.id, ftype.id) if f else ftype.id
                    fset_name = f.name if f else ''
                    new_sft_name = fset_name + '-' + ftype.name
                    new_sft = self._create_spatial_feature_type(f, new_sft_name , ftype.presentation)
                    remapped_sfts[remapped_sft_key] = new_sft.id
                    self.stdout.write(f'{ftype.name}:{ftype.id} remapped to {new_sft_name}:{new_sft.id}')
                self.num_ft += 1

    def _create_spatial_feature_type(self, featureset, type_name, type_presentation, type_id=None):
        dc = models.DisplayCategory.objects.get(id=featureset.id) if featureset else None
        values = dict(name=type_name,
                      presentation=type_presentation,
                      display_category=dc,
                      )
        func = getattr(models.SpatialFeatureType.objects, self.create_fn)
        result = func(id=type_id, defaults=values) if self.create_fn == 'update_or_create' \
            else func(id=type_id, **values)
        if isinstance(result, tuple):
            result = result[0]
        return result

    def migrate_features(self, all_features, remapped_sfts):
        self.stdout.write('Migrating Point, Line and Polygon features')
        # self.stdout.write(f'remapped_sfts: {remapped_sfts}')

        for f in all_features:
            remapped_sft_key = (f.featureset.id, f.type.id) if f.featureset else f.type.id
            remapped_sft_id = remapped_sfts.get(remapped_sft_key)
            # self.stdout.write(f'remapped sft_id {remapped_sft_id}')
            sft = models.SpatialFeatureType.objects.get(id=remapped_sft_id) \
                if remapped_sft_id else models.SpatialFeatureType.objects.get(id=f.type.id)
            values = dict(name=f.name,
                          feature_geometry=f.feature_geometry,
                          provenance=f.fields,
                          external_id=f.external_id,
                          feature_type=sft
                          )
            # self.stdout.write(f'processing {f.name} {f.id} {remapped_sft_id} {(f.featureset.id, f.type.id)}')
            try:
                with transaction.atomic():
                    func = getattr(models.SpatialFeature.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_f += 1
            except IntegrityError:
                if MigrateType.ErrorOnExisting == self.migrate_type:
                    raise ExistingFeatures(f'{f.id} {f.name} already exists')

    def migrate_spatialfiles(self):
        self.stdout.write('Migrating spatial files')

        for f in models.SpatialFile.objects.all():
            values = dict(
                name=f.name,
                description=f.description,
                layer_number=f.layer_number,
                name_field=f.name_field,
                id_field=f.id_field,
                file_type='shapefile',
            )
            try:
                with transaction.atomic():
                    func = getattr(models.SpatialFeatureFile.objects, self.create_fn)
                    func(id=f.id, defaults=values) if self.create_fn == 'update_or_create' else func(id=f.id, **values)
                    self.num_files += 1
            except IntegrityError:
                if MigrateType.ErrorOnExisting == self.migrate_type:
                    raise ExistingFeatures(f'{f.id} {f.name} already exists')

    def update_is_visible(self, feature_types, remapped_sft_ids):
        # only the newly migrated feature types should be visible in client UI, make others invisible
        if self.update_visible_flag:
            to_exclude = [f.id for f in feature_types] + remapped_sft_ids
            self.stdout.write('Hiding %d spatial feature types associated with analyzers' %
                              (models.SpatialFeatureType.objects.count() - len(to_exclude)))
            models.SpatialFeatureType.objects.exclude(id__in=to_exclude).update(is_visible=False)
        else:
            self.stdout.write("Append or Overwrite mode. Pre-existing SpatialFeatureType objects' is_visible flag not updated")
