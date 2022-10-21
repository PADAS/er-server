import logging

from django.contrib.gis.geos import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
from django.core.management import call_command
from faker import Faker

from core.tests import BaseAPITest
from mapping.models import FeatureSet, FeatureType, DisplayCategory, SpatialFeatureType, SpatialFeature, \
    PointFeature, LineFeature, PolygonFeature

logger = logging.getLogger(__name__)


class TestMigrateSpatial(BaseAPITest):
    faker = Faker()

    def test_migrate_new_features(self):
        road_fs = FeatureSet.objects.create(name=self.faker.name())
        water_fs = FeatureSet.objects.create(name=self.faker.name())
        main_road = FeatureType.objects.create(name=self.faker.name())
        side_road = FeatureType.objects.create(name=self.faker.name())
        river = FeatureType.objects.create(name=self.faker.name())
        lake = FeatureType.objects.create(name=self.faker.name())

        road_fs.types.add(main_road, side_road)
        water_fs.types.add(river, lake)

        p1, p2 = Point(0, 0), Point(1, 1)
        point = PointFeature.objects.create(name=self.faker.name(),
                                            type=main_road,
                                            featureset=road_fs,
                                            feature_geometry=MultiPoint(p1, p2))

        p3, p4 = Point(2, 2), Point(3, 3)
        l1, l2 = LineString(p1, p2), LineString(p3, p4)
        line = LineFeature.objects.create(name=self.faker.name(),
                                          type=side_road,
                                          featureset=road_fs,
                                          feature_geometry=MultiLineString(l1, l2))

        poly1 = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        poly2 = Polygon(((1, 1), (1, 2), (2, 2), (1, 1)))
        polygon = PolygonFeature.objects.create(name=self.faker.name(),
                                                type=river,
                                                featureset=water_fs,
                                                feature_geometry=MultiPolygon(poly1, poly2))

        call_command('migratespatial')

        self.assertEqual(2, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=road_fs.name))
        self.assertIsNotNone(DisplayCategory.objects.get(name=water_fs.name))

        self.assertEqual(4, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=main_road.name))
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=side_road.name))
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=river.name))
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=lake.name))

        self.assertEqual(3, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=point.name))
        self.assertIsNotNone(SpatialFeature.objects.get(name=line.name))
        self.assertIsNotNone(SpatialFeature.objects.get(name=polygon.name))

    def test_migrate_overwrite_existing(self):
        old_fs_name = self.faker.name()
        old_ft_name = self.faker.name()
        old_pt_name = self.faker.name()

        fs = FeatureSet.objects.create(name=old_fs_name)
        ft = FeatureType.objects.create(name=old_ft_name)
        fs.types.add(ft)

        p1, p2 = Point(0, 0), Point(1, 1)
        pt = PointFeature.objects.create(name=old_pt_name,
                                         type=ft,
                                         featureset=fs,
                                         feature_geometry=MultiPoint(p1, p2))

        call_command('migratespatial')

        self.assertEqual(1, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=fs.name))
        self.assertEqual(1, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=ft.name))
        self.assertEqual(1, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=pt.name))

        new_fs_name = self.faker.name()
        new_pt_name = self.faker.name()

        self.assertNotEqual(old_fs_name, new_fs_name)
        self.assertNotEqual(old_pt_name, new_pt_name)

        fs.name = new_fs_name
        pt.name = new_pt_name

        fs.save()
        pt.save()

        call_command('migratespatial', '--overwrite')

        self.assertEqual(1, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=new_fs_name))
        self.assertEqual(1, SpatialFeatureType.objects.count())
        self.assertEqual(1, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=new_pt_name))

    def test_migrate_append_new(self):
        old_fs_name = self.faker.name()
        old_ft_name = self.faker.name()
        old_pt_name = self.faker.name()

        fs = FeatureSet.objects.create(name=old_fs_name)
        ft = FeatureType.objects.create(name=old_ft_name)
        fs.types.add(ft)

        p1, p2 = Point(0, 0), Point(1, 1)
        pt = PointFeature.objects.create(name=old_pt_name,
                                         type=ft,
                                         featureset=fs,
                                         feature_geometry=MultiPoint(p1, p2))

        call_command('migratespatial')

        self.assertEqual(1, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=fs.name))
        self.assertEqual(1, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=ft.name))
        self.assertEqual(1, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=pt.name))

        new_fs_name = self.faker.name()
        new_ft_name = self.faker.name()
        new_pt_name = self.faker.name()

        self.assertNotEqual(old_fs_name, new_fs_name)
        self.assertNotEqual(old_ft_name, new_ft_name)
        self.assertNotEqual(old_pt_name, new_pt_name)

        fs = FeatureSet.objects.create(name=new_fs_name)
        ft = FeatureType.objects.create(name=new_ft_name)
        fs.types.add(ft)

        p1, p2 = Point(0, 0), Point(1, 1)
        PointFeature.objects.create(name=new_pt_name,
                                    type=ft,
                                    featureset=fs,
                                    feature_geometry=MultiPoint(p1, p2))

        call_command('migratespatial', '--append')

        self.assertEqual(2, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=new_fs_name))
        self.assertEqual(2, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=new_ft_name))
        self.assertEqual(2, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=new_pt_name))

    def test_migrate_unassigned_featuresets(self):
        FeatureSet.objects.create(name=self.faker.name())
        call_command('migratespatial')
        self.assertEqual(1, DisplayCategory.objects.count())

    def test_migrate_unassigned_featuretypes(self):
        fs = FeatureSet.objects.create(name=self.faker.name())
        ft = FeatureType.objects.create(name=self.faker.name())
        ft.featuresets.add(fs)

        call_command('migratespatial')

        self.assertEqual(1, DisplayCategory.objects.count())
        self.assertEqual(1, SpatialFeatureType.objects.count())

    def test_break_m2m(self):
        fs1 = FeatureSet.objects.create(name=self.faker.name())
        fs2 = FeatureSet.objects.create(name=self.faker.name())
        ft = FeatureType.objects.create(name=self.faker.name())
        ft.featuresets.add(fs1, fs2)

        p1, p2 = Point(0, 0), Point(1, 1)
        PointFeature.objects.create(name=self.faker.name(),
                                    type=ft,
                                    featureset=fs1,
                                    feature_geometry=MultiPoint(p1, p2))

        p1, p2 = Point(2, 2), Point(1, 1)
        PointFeature.objects.create(name=self.faker.name(),
                                    type=ft,
                                    featureset=fs2,
                                    feature_geometry=MultiPoint(p1, p2))

        call_command('migratespatial')

        self.assertEqual(2, DisplayCategory.objects.count())
        self.assertEqual(2, SpatialFeatureType.objects.count())  # should have created an extra sft
        self.assertEqual(2, SpatialFeature.objects.count())

        features = SpatialFeature.objects.all()
        self.assertNotEqual(features[0].feature_type.id, features[1].feature_type.id)

    def test_is_visible_after_migration(self):
        ft_names = [self.faker.name(), self.faker.name()]
        sft_names = [self.faker.name(), self.faker.name(), self.faker.name()]
        ft_names.sort()
        sft_names.sort()

        FeatureType.objects.bulk_create([FeatureType(name=ft_names[0]),
                                        FeatureType(name=ft_names[1])])
        SpatialFeatureType.objects.bulk_create([SpatialFeatureType(name=sft_names[0]),
                                               SpatialFeatureType(name=sft_names[1]),
                                               SpatialFeatureType(name=sft_names[2])])

        visible_qs = SpatialFeatureType.objects.filter(is_visible=True)
        invisible_qs = SpatialFeatureType.objects.filter(is_visible=False)
        visible_qs_names = [f.name for f in visible_qs]
        visible_qs_names.sort()

        self.assertEqual(3, visible_qs.count())
        self.assertEqual(0, invisible_qs.count())
        self.assertEqual(sft_names, visible_qs_names) # SFTs are visible by default

        call_command('migratespatial')

        visible_qs = SpatialFeatureType.objects.filter(is_visible=True)
        invisible_qs = SpatialFeatureType.objects.filter(is_visible=False)
        visible_qs_names = [f.name for f in visible_qs]
        invisible_qs_names = [f.name for f in invisible_qs]
        visible_qs_names.sort()
        invisible_qs_names.sort()

        self.assertEqual(2, visible_qs.count())
        self.assertEqual(3, invisible_qs.count())
        self.assertEqual(ft_names, visible_qs_names)  # migrated FTs are visible
        self.assertEqual(sft_names, invisible_qs_names)  # SFTs that existed before migration are now invisible

