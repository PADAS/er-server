from __future__ import annotations

import pytest

from mapping.models import DisplayCategory, SpatialFeatureType


@pytest.fixture
def category1() -> DisplayCategory:
    return DisplayCategory.objects.create(name="Category One")


@pytest.fixture
def category2() -> DisplayCategory:
    return DisplayCategory.objects.create(name="Category Two")


@pytest.fixture
def feature_type1(category1: DisplayCategory) -> SpatialFeatureType:
    return SpatialFeatureType.objects.create(name="Type One", display_category=category1)


@pytest.fixture
def feature_type2(category2: DisplayCategory) -> SpatialFeatureType:
    return SpatialFeatureType.objects.create(name="Type Two", display_category=category2)
