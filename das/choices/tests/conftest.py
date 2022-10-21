import pytest

from choices.tests.factories import ChoiceFactory


@pytest.fixture
def choice():
    return ChoiceFactory.create()
