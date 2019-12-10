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
                                            feature_geometry=MultiPoint(p1, p2))

        p3, p4 = Point(2, 2), Point(3, 3)
        l1, l2 = LineString(p1, p2), LineString(p3, p4)
        line = LineFeature.objects.create(name=self.faker.name(),
                                          type=side_road,
                                          feature_geometry=MultiLineString(l1, l2))

        poly1 = Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)))
        poly2 = Polygon(((1, 1), (1, 2), (2, 2), (1, 1)))
        polygon = PolygonFeature.objects.create(name=self.faker.name(),
                                                type=river,
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

        fs.name = new_fs_name
        ft.name = new_ft_name
        pt.name = new_pt_name

        fs.save()
        ft.save()
        pt.save()

        call_command('migratespatial', '--overwrite')

        self.assertEqual(1, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=new_fs_name))
        self.assertEqual(1, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=new_ft_name))
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
        pt = PointFeature.objects.create(name=new_pt_name,
                                         type=ft,
                                         feature_geometry=MultiPoint(p1, p2))

        call_command('migratespatial', '--append')

        self.assertEqual(2, DisplayCategory.objects.count())
        self.assertIsNotNone(DisplayCategory.objects.get(name=new_fs_name))
        self.assertEqual(2, SpatialFeatureType.objects.count())
        self.assertIsNotNone(SpatialFeatureType.objects.get(name=new_ft_name))
        self.assertEqual(2, SpatialFeature.objects.count())
        self.assertIsNotNone(SpatialFeature.objects.get(name=new_pt_name))
