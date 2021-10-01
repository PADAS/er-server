import pytest

from factories import (
    PatrolFactory,
    PatrolNoteFactory,
    PatrolSegmentFactory,
    PatrolSegmentSubjectFactory,
    PatrolSegmentUserFactory
)


@pytest.fixture
def patrol():
    PatrolFactory()


@pytest.fixture
def five_patrols():
    PatrolFactory.create_batch(5)


@pytest.fixture
def five_patrol_notes():
    PatrolNoteFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment():
    PatrolSegmentFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_subject():
    PatrolSegmentSubjectFactory.create_batch(5)


@pytest.fixture
def five_patrol_segment_user():
    PatrolSegmentUserFactory.create_batch(5)
