from django.test import TestCase

from mapping.models import DisplayCategory, SpatialFeatureType


# TODO: Kezzy. Is this base class needed? Can setUp be moved to the child class?
class BaseTest(TestCase):

    def setUp(self):
        super().setUp()

        display_category = DisplayCategory.objects.create(name="test_category")

        SpatialFeatureType.objects.bulk_create({
            SpatialFeatureType(name="Soft-Field Airstrip",
                               display_category=display_category),
            SpatialFeatureType(
                name="Airstrip", display_category=display_category),
        })
