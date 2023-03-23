import pytest

from accounts.utils import fetch_organization_choices, fetch_tech_choices


@pytest.mark.django_db
class TestUtils:
    def test_fetch_tech_choices(self, five_choices):
        five_choices[0].field = "tech"
        five_choices[0].save()
        five_choices[1].field = "tech"
        five_choices[1].save()

        tech_choices = fetch_tech_choices()

        assert tech_choices == (("value_0", "display_0"), ("value_1", "display_1"))

    def test_fetch_empty_tech_choices(self):
        tech_choices = fetch_tech_choices()

        assert tech_choices == ()


@pytest.mark.django_db
class TestFetchOrganizationChoices:
    def test_fetch_organization_choices(self, five_choices):
        five_choices[0].field = "organization"
        five_choices[0].save()
        five_choices[1].field = "organization"
        five_choices[1].save()

        tech_choices = fetch_organization_choices()

        assert tech_choices == (("", ""), ("value_5", "display_5"), ("value_6", "display_6"))

    def test_fetch_empty_organization_choices(self):
        tech_choices = fetch_organization_choices()

        assert tech_choices == (("", ""),)
