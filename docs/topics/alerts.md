# Alerts

Alerts notify users when events matching specific criteria are created or updated in EarthRanger. Users configure **Alert Rules** that define which event types, conditions, and notification methods trigger an alert.

## Overview

The alert pipeline follows this flow:

1. An **Event** is created or updated.
2. A post-save signal queues a Celery task to evaluate the event against active alert rules.
3. Each **Alert Rule** whose event type and schedule match is evaluated.
4. If the event satisfies the rule's conditions (or the rule is unconditional), notifications are dispatched.
5. Each **Notification Method** (email, SMS, or WhatsApp) on the rule receives the alert.

## Alert Rules

An alert rule defines:

| Field | Description |
|---|---|
| **Title** | A human-readable name for the rule. |
| **Event Types** | One or more event types the rule applies to. |
| **Conditions** | Optional filter criteria (e.g., priority = Red, title contains "poaching"). When no conditions are set the rule fires on every matching event. |
| **Schedule** | A weekly schedule with timezone controlling when the rule is active. If the event occurs outside the schedule window, the alert is suppressed. |
| **Notification Methods** | One or more destinations (email addresses, phone numbers) that receive the alert. |
| **Override Message** | Optional custom message body that replaces the default alert template for email and SMS. |
| **Order Number** | Controls evaluation precedence when multiple rules match. |
| **Is Active** | Toggle to enable or disable the rule without deleting it. |

Alert rules are scoped to an **owner** (the user who created the rule). Only events visible to that owner are evaluated.

### Conditions

Conditions use a business-rules engine to filter events by their fields. A condition set is a JSON structure with either:

- `"all"` — every condition must be true (AND logic).
- `"anyOf"` — at least one condition must be true (OR logic).

Each condition specifies a **variable** (event field), an **operator**, and a **value**.

#### Available Operators by Field Type

| Field Type | Operator | Display Label |
|---|---|---|
| Numeric | `equal_to` | = |
| Numeric | `greater_than` | > |
| Numeric | `less_than` | < |
| Numeric | `greater_than_or_equal_to` | &ge; |
| Numeric | `less_than_or_equal_to` | &le; |
| Select (multiple) | `shares_at_least_one_element_with` | Is One Of |
| Select (multiple) | `shares_no_elements_with` | Is Not One Of |
| String | `contains` | Includes |
| String | `non_empty` | Is Not Empty |

#### Built-in Variables

Every alert rule can filter on these core event fields:

- **Title** (string) — the event title.
- **Priority** (select) — Red, Amber, or Green.
- **State** (select) — new, active, or resolved.
- **Subject Group** (select) — groups associated with the event's related subjects.

Additional variables are dynamically generated from the event type's schema (e.g., custom fields defined in event type properties).

### Unconditional Rules

When an alert rule has no conditions, it fires for **every** event of the configured event types that occurs within the rule's schedule.

### Conditional Rules on Update

When an existing event is updated, the system checks whether the updated fields are relevant to the rule's conditions. If none of the changed fields match condition variables, the alert is skipped to avoid duplicate notifications.

## Notification Methods

A notification method defines how and where an alert is delivered.

| Method | Value | Notes |
|---|---|---|
| **Email** | Email address | Sends an HTML alert with event details and a link to the event. |
| **SMS** | Phone number (E.164) | Sends a text message with a condensed alert summary. |
| **WhatsApp** | Phone number (E.164) | Sends a structured WhatsApp message via template. |

Each notification method is owned by a user and can be shared across multiple alert rules.

## Alert Content

Alerts include the following information:

- **Event title** and **serial number** (Report ID).
- **Priority** with color indicator (Red, Amber, Green).
- **State** (New, Active, or Resolved) with inferred state logic.
- **Event time** and **alert time**.
- **Location** — longitude and latitude with a deep link to the map view (if the event has a location).
- **Reported by** — the user or entity that created the event.
- **Event details** — custom schema fields with display-friendly titles and values.
- **Changed fields** — when an event is updated, the alert highlights which fields changed and their previous values.
- **Notes** — any notes attached to the event, with an indicator for recently updated notes.
- **Alert rule name** and **site name/URL**.

When an alert rule has an **override message**, that message replaces the default template body for email and SMS alerts.

## Rate Limiting

To prevent alert fatigue and protect notification channels, EarthRanger enforces per-user rate limits on alerts.

- Each user has a configurable **alert rate limit** (set in tenant environment settings).
- A counter tracks the number of alerts sent to each user within a rolling time window (configured via `ALERTS_RATE_LIMIT_DURATION_SECONDS`).
- When the counter reaches the limit, further alerts are suppressed until the window resets.
- When a user is approaching their limit (within `ALERTS_REMAINING_COUNTER_FOR_WARNING` alerts), a warning is prepended to the alert title showing how many alerts remain.
- Alert usage metrics are published for monitoring: gauges track users at 90% and 100% of their quota.

## Schedules

Alert rules support a weekly schedule that controls when alerts are active. The schedule is defined as a JSON object conforming to the `OneWeekSchedule` schema and includes a timezone. Events that occur outside the scheduled windows do not trigger alerts for that rule.

## Permissions and Location Visibility

### Two Users, Two Roles

Alert permissions involve **two distinct users** whose roles are easy to confuse:

| User | Role in the Pipeline |
|---|---|
| **Alert rule owner** | Determines which event types and conditions trigger the alert. The rule is only evaluated if the owner's account is active. |
| **Notification method owner** | Determines whether the event can actually be rendered and sent. The event is permission-checked against **this user's** access, not the alert rule owner's. |

These are often the same person, but they do not have to be. A notification method can be shared across multiple alert rules owned by different users.

### How Permissions Are Applied

The pipeline applies permissions at two stages:

**1. Rule evaluation (superuser context):** When an event is created or updated, the system evaluates it against all matching alert rules using a **synthetic superuser**. This deliberately ignores per-user restrictions so that rules are evaluated uniformly. The code comment notes: *"I will leave it up to the logic that sends alerts to determine whether an individual user has read access."*

**2. Alert rendering (notification method owner context):** When the alert is actually sent, the event is re-rendered using the **notification method owner** as the permission context. The following checks apply:

- **Event category permission** — the notification method owner must have read access to the event's category (e.g., `security_read`, `monitoring_read`).
- **Subject group membership** — if the event has related subjects, those subjects must belong to subject groups the notification method owner has permission to view.

If either check fails, the alert is **silently skipped** for that notification method — no error is raised and no notification is sent.

### Practical Implications

Because permissions are checked against the notification method owner:

- An alert rule owner can configure a rule that matches events they themselves can see, but if the notification method belongs to a user without the right event category or subject group permissions, that notification will never fire.
- Conversely, if a notification method owner has broader permissions than the alert rule owner, alerts will be sent based on the notification method owner's access.
- When troubleshooting "why didn't my alert fire?", check the permissions of **both** the alert rule owner (is their account active?) and the notification method owner (can they see this event category and its related subjects?).

### Location in Alerts

**Important:** When an alert is sent, the event's location is included directly from the event record. The alert pipeline does **not** apply subject-level location permissions (such as `view_last_position` or `view_real_time`) when rendering event data for alerts.

This means that if the notification method owner:
- Passes the event category permission check, and
- Has access to the related subject groups,

they **will receive the event's location in the alert**, even if they would not normally have permission to view that subject's real-time location through the observations API.

The location included in the alert is the **event location** (where the event was reported), not the subject's current tracking position. However, for events generated from real-time tracking data (e.g., geofence breaks, immobility alerts), the event location typically reflects the subject's position at the time the event was created.

## Pipeline Architecture

The alert system uses Celery for asynchronous processing:

```
Event saved
  → post_save signal (activity/signals.py)
    → evaluate_alert_rules task (activity/tasks.py)
      → evaluate_event (activity/alerting/service.py)
        → business rules evaluation (activity/alerting/businessrules.py)
          → evaluate_conditions_for_sending_alerts (activity/tasks.py)
            → send_alert_to_notificationmethod task (activity/tasks.py)
              → send_event_alert (activity/alerting/message.py)
```

Each `send_alert_to_notificationmethod` task is dispatched as a separate Celery task, allowing independent rate limiting and retry behavior per notification method.
