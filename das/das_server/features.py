import enum

FEATURES = {
    "FEATURE_EVENT_GEOMETRIES": 0
}


class Features(enum.Enum):
    EVENT_GEOMETRIES = "FEATURE_EVENT_GEOMETRIES"


class FeatureFlags:
    def __init__(self):
        self._features = {
            Features.EVENT_GEOMETRIES: self._get_flag(
                Features.EVENT_GEOMETRIES.value)
        }

    def _get_flag(self, flag_name):
        # TO IMPROVE Remove the FEATURES var and get them from the environment
        return bool(FEATURES.get(flag_name, 0))

    @property
    def use_polygons(self):
        return self._features[Features.EVENT_GEOMETRIES]
