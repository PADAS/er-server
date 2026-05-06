import json

import pytest

from mapping.forms import DisplayCategoryForm, SpatialFeatureTypeForm
from mapping.models import DisplayCategory, SpatialFeatureType


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSpatialFeatureTypeFormExtraKeys:
    """Extra keys in the presentation JSON that have no corresponding UI control must survive a form save."""

    @pytest.fixture
    def category(self):
        return DisplayCategory.objects.create(name="Cat")

    @pytest.fixture
    def feature_type_with_extra_keys(self, category):
        return SpatialFeatureType.objects.create(
            name="FT Extra",
            display_category=category,
            presentation={
                "stroke": "#ff0000",
                "stroke-width": 3,
                "custom-key": "preserved",
                "another-extra": 42,
            },
        )

    def _submit_form(self, instance, overrides=None):
        """Build a minimal valid POST payload for SpatialFeatureTypeForm and save it."""
        presentation = instance.presentation or {}
        data = {
            "id": str(instance.pk),
            "das_tenant": str(instance.das_tenant_id),
            "name": instance.name,
            "is_visible": True,
            # Simple formatting controls matching the form fields
            "stroke": presentation.get("stroke", "#FF6600"),
            "stroke_width": presentation.get("stroke-width", 2),
            "stroke_opacity": presentation.get("stroke-opacity", 1),
            "point_image": presentation.get("image", ""),
            "point_width": presentation.get("width", 20),
            "point_height": presentation.get("height", 20),
            "fill_opacity": presentation.get("fill-opacity", 0.25),
            "fill_outline_color": presentation.get("fill-outline-color", "#FF6600"),
            "fill_color": presentation.get("fill", "#FF6600"),
            # The textarea carries the full JSON (as the JS would produce it).
            "presentation": json.dumps(presentation),
        }
        if overrides:
            data.update(overrides)
        form = SpatialFeatureTypeForm(data=data, instance=instance)
        assert form.is_valid(), form.errors
        return form.save()

    def test_extra_keys_preserved_when_simple_fields_submitted(self, feature_type_with_extra_keys):
        """Submitting the form with extra keys in the JSON textarea keeps them on the saved instance."""
        saved = self._submit_form(feature_type_with_extra_keys)
        saved.refresh_from_db()
        assert saved.presentation["custom-key"] == "preserved"
        assert saved.presentation["another-extra"] == 42

    def test_simple_field_changes_do_not_remove_extra_keys(self, feature_type_with_extra_keys):
        """Changing a simple UI control while extra keys are in the JSON keeps those extra keys."""
        presentation_with_change = dict(feature_type_with_extra_keys.presentation)
        presentation_with_change["stroke"] = "#00ff00"

        saved = self._submit_form(
            feature_type_with_extra_keys,
            overrides={"stroke": "#00ff00", "presentation": json.dumps(presentation_with_change)},
        )
        saved.refresh_from_db()
        assert saved.presentation["stroke"] == "#00ff00"
        assert saved.presentation["custom-key"] == "preserved"
        assert saved.presentation["another-extra"] == 42

    def test_legacy_fill_color_loaded_into_fill_color_field(self, category):
        """Legacy presentation using "fill-color" should populate the fill_color editor field."""
        instance = SpatialFeatureType.objects.create(
            name="FT Legacy Fill",
            display_category=category,
            presentation={"fill-color": "#abc123"},
        )
        form = SpatialFeatureTypeForm(instance=instance)
        assert form.initial["fill_color"] == "#abc123"

    def test_fill_takes_precedence_over_legacy_fill_color(self, category):
        """If both keys are present, the canonical "fill" wins."""
        instance = SpatialFeatureType.objects.create(
            name="FT Both",
            display_category=category,
            presentation={"fill": "#111111", "fill-color": "#222222"},
        )
        form = SpatialFeatureTypeForm(instance=instance)
        assert form.initial["fill_color"] == "#111111"

    def test_save_drops_legacy_fill_color_when_fill_is_set(self, category):
        """Saving a legacy feature_type through the editor migrates "fill-color" forward to "fill"."""
        instance = SpatialFeatureType.objects.create(
            name="FT Legacy Upgrade",
            display_category=category,
            presentation={"fill-color": "#abc123"},
        )
        # Mimic the JS textarea sync: the legacy key sits alongside the new canonical key.
        synced_presentation = {"fill-color": "#abc123", "fill": "#abc123"}
        saved = self._submit_form(
            instance,
            overrides={"fill_color": "#abc123", "presentation": json.dumps(synced_presentation)},
        )
        saved.refresh_from_db()
        assert saved.presentation["fill"] == "#abc123"
        assert "fill-color" not in saved.presentation


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDisplayCategoryFormFeatureClasses:
    """The custom feature_classes field must persist through the admin commit=False / save_m2m() flow."""

    def test_feature_classes_persist_when_saved_with_commit_false(self):
        category = DisplayCategory.objects.create(name="Cat A")
        ft1 = SpatialFeatureType.objects.create(name="FT1")
        ft2 = SpatialFeatureType.objects.create(name="FT2")

        form = DisplayCategoryForm(
            data={
                "id": str(category.pk),
                "name": category.name,
                "feature_classes": [str(ft1.pk), str(ft2.pk)],
                "description": "",
            },
            instance=category,
        )
        assert form.is_valid(), form.errors

        # Mimic the Django admin save flow: save(commit=False), instance.save(), form.save_m2m().
        instance = form.save(commit=False)
        instance.save()
        form.save_m2m()

        ft1.refresh_from_db()
        ft2.refresh_from_db()
        assert ft1.display_category_id == category.pk
        assert ft2.display_category_id == category.pk

    def test_feature_classes_replaces_existing_assignments(self):
        category = DisplayCategory.objects.create(name="Cat B")
        previously_assigned = SpatialFeatureType.objects.create(name="FT Old", display_category=category)
        newly_assigned = SpatialFeatureType.objects.create(name="FT New")

        form = DisplayCategoryForm(
            data={
                "id": str(category.pk),
                "name": category.name,
                "feature_classes": [str(newly_assigned.pk)],
                "description": "",
            },
            instance=category,
        )
        assert form.is_valid(), form.errors

        instance = form.save(commit=False)
        instance.save()
        form.save_m2m()

        previously_assigned.refresh_from_db()
        newly_assigned.refresh_from_db()
        assert previously_assigned.display_category_id is None
        assert newly_assigned.display_category_id == category.pk

    def test_feature_classes_persist_when_saved_with_commit_true(self):
        category = DisplayCategory.objects.create(name="Cat C")
        ft = SpatialFeatureType.objects.create(name="FT Direct")

        form = DisplayCategoryForm(
            data={
                "id": str(category.pk),
                "name": category.name,
                "feature_classes": [str(ft.pk)],
                "description": "",
            },
            instance=category,
        )
        assert form.is_valid(), form.errors

        form.save(commit=True)

        ft.refresh_from_db()
        assert ft.display_category_id == category.pk

    def test_feature_classes_cleared_when_none_selected(self):
        category = DisplayCategory.objects.create(name="Cat D")
        previously_assigned = SpatialFeatureType.objects.create(name="FT To Clear", display_category=category)

        form = DisplayCategoryForm(
            data={
                "id": str(category.pk),
                "name": category.name,
                "feature_classes": [],
                "description": "",
            },
            instance=category,
        )
        assert form.is_valid(), form.errors

        instance = form.save(commit=False)
        instance.save()
        form.save_m2m()

        previously_assigned.refresh_from_db()
        assert previously_assigned.display_category_id is None
