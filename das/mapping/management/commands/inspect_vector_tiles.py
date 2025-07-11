"""
Management command to inspect and test vector tile configuration.
"""

from django.core.management.base import BaseCommand

from mapping.models import SpatialFeature
from mapping.vector_layers import SpatialFeatureLayer


class Command(BaseCommand):
    help = "Inspect vector tile configuration for SpatialFeature"

    def add_arguments(self, parser):
        parser.add_argument(
            "--show-filters",
            action="store_true",
            help="Show available filter information",
        )
        parser.add_argument(
            "--test-filtering",
            action="store_true",
            help="Test the filtering functionality",
        )
        parser.add_argument(
            "--count-features",
            action="store_true",
            help="Show count of spatial features",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("SpatialFeature Vector Tile Configuration"))
        self.stdout.write("=" * 50)

        layer = SpatialFeatureLayer()

        # Basic layer information
        self.stdout.write(f"Layer ID: {layer.id}")
        self.stdout.write(f"Model: {layer.model.__name__}")
        self.stdout.write(f"Geometry Field: {layer.geometry_field}")
        self.stdout.write(f"FilterSet Class: {layer.filterset_class.__name__}")
        self.stdout.write(f"Min Zoom: {layer.min_zoom}")
        self.stdout.write(f"Max Zoom: {layer.max_zoom}")
        self.stdout.write(f"Tile Fields: {', '.join(layer.tile_fields)}")
        self.stdout.write("")

        if options["show_filters"]:
            self.show_filter_information(layer)

        if options["count_features"]:
            self.show_feature_counts()

        if options["test_filtering"]:
            self.test_filtering(layer)

    def show_filter_information(self, layer):
        """Display information about available filters."""
        self.stdout.write(self.style.WARNING("Available Filters:"))
        self.stdout.write("-" * 30)

        filter_info = layer.get_filter_info()

        if not filter_info:
            self.stdout.write("No filters configured")
            return

        for param_name, info in filter_info.items():
            self.stdout.write(f"Parameter: {param_name}")
            self.stdout.write(f"  Field Name: {info['field_name']}")
            self.stdout.write(f"  Filter Type: {info['filter_type']}")
            self.stdout.write(f"  Label: {info['label']}")
            self.stdout.write(f"  Supports CSV: {info['supports_csv']}")
            if info["help_text"]:
                self.stdout.write(f"  Help: {info['help_text']}")
            self.stdout.write("")

    def show_feature_counts(self):
        """Display counts of spatial features."""
        self.stdout.write(self.style.WARNING("Feature Counts:"))
        self.stdout.write("-" * 20)

        try:
            total_features = SpatialFeature.objects.count()
            self.stdout.write(f"Total SpatialFeatures: {total_features}")

            # Count by feature type if available
            feature_types = SpatialFeature.objects.values("feature_type__name").distinct().count()
            self.stdout.write(f"Distinct Feature Types: {feature_types}")

            # Count by display category if available
            display_categories = (
                SpatialFeature.objects.values("feature_type__display_category__name").distinct().count()
            )
            self.stdout.write(f"Distinct Display Categories: {display_categories}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error counting features: {e}"))

        self.stdout.write("")

    def test_filtering(self, layer):
        """Test the filtering functionality."""
        self.stdout.write(self.style.WARNING("Testing Filtering:"))
        self.stdout.write("-" * 20)

        # Test with empty parameters
        layer.request_params = {}
        try:
            qs1 = layer.get_vector_tile_queryset(10, 100, 100)
            count1 = qs1.count()
            self.stdout.write(f"No filters: {count1} features")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error with no filters: {e}"))

        # Test with sample parameters (if features exist)
        try:
            # Get a sample feature type ID for testing
            sample_feature = SpatialFeature.objects.select_related("feature_type").first()

            if sample_feature and sample_feature.feature_type:
                test_params = {"feature_class": str(sample_feature.feature_type.id)}
                layer.request_params = test_params

                qs2 = layer.get_vector_tile_queryset(10, 100, 100)
                count2 = qs2.count()
                self.stdout.write(f"With feature_class filter ({sample_feature.feature_type.id}): {count2} features")
            else:
                self.stdout.write("No sample features available for testing")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error testing filters: {e}"))

        self.stdout.write("")

    def style_success(self, message):
        """Helper for success styling."""
        return f"\033[92m{message}\033[0m"

    def style_warning(self, message):
        """Helper for warning styling."""
        return f"\033[93m{message}\033[0m"

    def style_error(self, message):
        """Helper for error styling."""
        return f"\033[91m{message}\033[0m"
