from __future__ import annotations

import secrets


def make_random_password() -> str:
    return secrets.token_urlsafe(16)
