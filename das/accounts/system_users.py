# Single source of truth for usernames for automatically generated system users.
# These constants are imported by the various modules that create these users and also by
# database migrations (e.g. accounts/migrations/0062_populate_is_system_for_existing_users.py).

ER_SYSTEM_USER = "er_system"
SYSTEM_ANALYZERS_USER = "system_analyzers"
GFW_WEBHOOK_USER = "gfwwebhookuser"
DAS_OAUTH_ACT_USER = "das_oauth_act"
DELETED_SENTINEL_USER = "deleted"

SYSTEM_USERNAMES = [
    ER_SYSTEM_USER,
    SYSTEM_ANALYZERS_USER,
    GFW_WEBHOOK_USER,
    DAS_OAUTH_ACT_USER,
    DELETED_SENTINEL_USER,
]
