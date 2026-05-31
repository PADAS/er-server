from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.tenant.thread import get_tenant_settings


@dataclass(frozen=True)
class ReleaseToggle:
    """A per-tenant release toggle with an optional global override.

    A release toggle (in the sense of Martin Fowler's feature-toggle taxonomy)
    lets an incomplete or latent feature be merged to mainline and deployed
    while kept dark, then flipped on per-tenant and eventually for everyone
    once it's ready — and removed once the rollout is complete.

    Resolution precedence when the toggle is read (see ``get_release_toggle``):

    1. ``global_override`` — if not ``None``, this value wins for **every**
       tenant, regardless of what TMS sent. It is the "make it public for
       everyone" / "emergency kill" lever: flip it in an ER code change rather
       than touching every tenant.
    2. The per-tenant value from the tenant payload's ``releaseToggles`` block
       (set through TMS, no release required).
    3. ``default`` — the registered fallback when a tenant hasn't set a value.
    """

    default: Any = False
    description: str = ""
    global_override: Any = None


RELEASE_TOGGLES: dict[str, ReleaseToggle] = {
    "community_input_admin_enabled": ReleaseToggle(
        default=False,
        description="Per-tenant gate for the Community Input Django admin page. "
        "Set global_override=True to expose it for every tenant at once.",
    ),
}


class UnknownReleaseToggle(KeyError):
    """Raised when a toggle name is read but isn't declared in RELEASE_TOGGLES."""


def get_release_toggle(name: str) -> Any:
    if name not in RELEASE_TOGGLES:
        raise UnknownReleaseToggle(
            f"Release toggle {name!r} is not registered in RELEASE_TOGGLES "
            "(see das/utils/tenant/release_toggles.py)."
        )
    toggle = RELEASE_TOGGLES[name]
    if toggle.global_override is not None:
        return toggle.global_override
    values = getattr(get_tenant_settings(), "release_toggles", None) or {}
    return values.get(name, toggle.default)
