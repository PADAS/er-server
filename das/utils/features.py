import enum
from dataclasses import dataclass

import environ

BASE_DIR = environ.Path(__file__) - 2
env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)

environ.Env.read_env(BASE_DIR(".env"))


class Features(enum.Enum):
    FEATURE_TMS = "tms"


@dataclass(frozen=True)
class Feature:
    _is_on: bool = False

    def is_on(self):
        return self._is_on


class FeatureFlags:
    def __init__(self):
        self._features = {Features.FEATURE_TMS.value: Feature(self._get_flag(Features.FEATURE_TMS.value))}

    def __getattr__(self, feature_name):
        try:
            return self._features[feature_name]
        except KeyError:
            raise Exception(f"Feature {feature_name} is not defined yet.")

    def _get_flag(self, flag_name):
        try:
            return env.bool(f"FEATURE_{flag_name}".upper(), False)
        except ValueError:
            return False


features = FeatureFlags()

__all__ = ["features"]
