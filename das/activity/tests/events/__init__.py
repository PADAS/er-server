"""Common constants for event tests."""

ET_OTHER = "other"

ET_CARCASS = "carcass_rep"
ET_SECURITY = ET_CARCASS
ET_MONITORING = "wildlife_sighting_rep"
ET_LOGISTICS = "all_posts"

# These permission lists are made up, and do not necessarily correspond to permission sets in production deployments
# All perms user has... all perms
all_permissions = [
    "security_create",
    "security_read",
    "security_update",
    "security_delete",
    "monitoring_create",
    "monitoring_read",
    "monitoring_update",
    "monitoring_delete",
    "logistics_create",
    "logistics_read",
    "logistics_update",
    "logistics_delete",
]
# Power user has all access to logistics and monitoring events, but can only
# read security events
power_user_permissions = [
    "security_read",
    "monitoring_create",
    "monitoring_read",
    "monitoring_update",
    "monitoring_delete",
    "logistics_create",
    "logistics_read",
    "logistics_update",
    "logistics_delete",
]
# Radio room users can create any type of event, view/update monitoring and
# logistics events, and delete nothing
radio_room_user_permissions = [
    "security_create",
    "monitoring_create",
    "monitoring_read",
    "monitoring_update",
    "logistics_create",
    "logistics_read",
    "logistics_update",
]

eventsource_user_permissions = [
    "add_eventsource",
    "change_eventsource",
    "delete_eventsource",
    "create_event_for_eventsource",
]

eventsource_user_event_permissions = [
    "security_create",
]

# Guest users can see logistics events and nothing else
guest_user_permissions = ["logistics_read"]

reported_by_permission_set_id = "b5057387-9f6c-4685-8ec1-46ad29684eea"
