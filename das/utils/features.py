import enum
import os
from dataclasses import dataclass


class Features(enum.Enum):
    pass


@dataclass(frozen=True)
class Feature:
    _is_on: bool = False

    def is_on(self):
        return self._is_on


class FeatureFlags:
    def __init__(self):
        self._features = {}

    def __getattr__(self, feature_name):
        try:
            return self._features[feature_name]
        except KeyError:
            raise Exception(f"Feature {feature_name} is not defined yet.")

    def _get_flag(self, flag_name):
        try:
            return os.getenv(f"FEATURE_{flag_name}".upper(), "False").lower() in ["true"]
        except ValueError:
            return False


features = FeatureFlags()

__all__ = ["features"]
