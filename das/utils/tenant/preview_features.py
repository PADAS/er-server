from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.tenant.thread import get_tenant_settings


@dataclass(frozen=True)
class PreviewFeature:
    """A per-tenant preview feature with an optional global override.

    A preview feature (in the sense of Martin Fowler's release-toggle taxonomy)
    lets an incomplete or latent feature be merged to mainline and deployed
    while kept dark, then flipped on per-tenant and eventually for everyone
    once it's ready — and removed once the rollout is complete.

    Resolution precedence when the feature is read (see ``get_preview_feature``):

    1. ``global_override`` — if not ``None``, this value wins for **every**
       tenant, regardless of what TMS sent. It is the "make it public for
       everyone" / "emergency kill" lever: flip it in an ER code change rather
       than touching every tenant.
    2. The per-tenant value from the tenant payload's ``previewFeatures`` block
       (set through TMS, no release required).
    3. ``default`` — the registered fallback when a tenant hasn't set a value.
    """

    default: Any = False
    description: str = ""
    global_override: Any = None


PREVIEW_FEATURES: dict[str, PreviewFeature] = {
    "community_input_admin_enabled": PreviewFeature(
        default=False,
        description="Per-tenant gate for the Community Input Django admin page. "
        "Set global_override=True to expose it for every tenant at once.",
    ),
    "attachment_property": PreviewFeature(
        default=False,
        description="Per-tenant gate for the eventtype V2 attachment properties. "
        "Stays off until all clients support the attachment property feature; "
        "set global_override=True to expose it for every tenant at once.",
    ),
}


class UnknownPreviewFeature(KeyError):
    """Raised when a feature name is read but isn't declared in PREVIEW_FEATURES."""


def get_preview_feature(name: str) -> Any:
    if name not in PREVIEW_FEATURES:
        raise UnknownPreviewFeature(
            f"Preview feature {name!r} is not registered in PREVIEW_FEATURES "
            "(see das/utils/tenant/preview_features.py)."
        )
    feature = PREVIEW_FEATURES[name]
    if feature.global_override is not None:
        return feature.global_override
    values = getattr(get_tenant_settings(), "preview_features", None) or {}
    return values.get(name, feature.default)


def get_resolved_preview_features() -> dict[str, Any]:
    """Resolve every registered preview feature to its current value for this tenant.

    Reads the tenant preview-features dict once and applies global_override /
    per-tenant / default precedence inline in a single pass over PREVIEW_FEATURES.
    All registered features are always present in the returned dict.
    """
    tenant_values: dict[str, Any] = getattr(get_tenant_settings(), "preview_features", None) or {}
    result: dict[str, Any] = {}
    for name, feature in PREVIEW_FEATURES.items():
        if feature.global_override is not None:
            result[name] = feature.global_override
        else:
            result[name] = tenant_values.get(name, feature.default)
    return result
