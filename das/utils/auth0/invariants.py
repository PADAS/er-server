from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def required(value: T | None, *, field: str) -> T:
    """Narrow an Optional value, raising ValueError when None.

    Use this to bridge auth0-python v5 Pydantic response models that
    declare fields as Optional even when the API guarantees them on 2xx.
    """
    if value is None:
        raise ValueError(f"Expected non-None value for '{field}'")
    return value
