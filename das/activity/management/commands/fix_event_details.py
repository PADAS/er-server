from __future__ import annotations

import copy
import json
import logging
import uuid
from enum import Enum
from typing import Callable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from activity.models import EventDetails
from utils.tenant.commands import TenantCommandMixin

logger = logging.getLogger(__name__)

# The outer key that wraps the actual property dict inside EventDetails.data.
EVENT_DETAILS_KEY = "event_details"

# A transform function receives a deep-copied event_details dict and returns
# either a modified copy (change needed) or None (no change needed / skip).
TransformFn = Callable[[dict], dict | None]


class Transform(str, Enum):
    WRAP_IN_ARRAY = "wrap-in-array"
    UNWRAP_SINGLE_ARRAY = "unwrap-single-array"
    COERCE_TYPE = "coerce-type"
    SET_VALUE = "set-value"
    RENAME_KEY = "rename-key"
    DELETE_KEY = "delete-key"


class CoerceToType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"


def _coerce_string(value: object) -> str:
    return str(value)


def _coerce_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"cannot coerce {type(value).__name__} to integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"cannot coerce non-integral float {value!r} to integer")
    return int(value)


def _coerce_number(value: object) -> int | float:
    """Coerce to an int when the value is integral, else a float.

    JSON Schema's ``number`` type accepts integers as well as floats, so a
    plain ``float()`` coercion would needlessly turn ``"3"`` into ``3.0`` —
    and, conversely, fractional values must be preserved rather than
    truncated via ``int()``.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"cannot coerce {type(value).__name__} to number")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    # value is a str at this point.
    try:
        return int(value)
    except ValueError:
        return float(value)


_TRUE_STRINGS = frozenset({"true", "1", "yes"})
_FALSE_STRINGS = frozenset({"false", "0", "no"})


def _coerce_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"cannot coerce {value!r} to boolean")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        raise ValueError(f"cannot coerce {value!r} to boolean")
    raise TypeError(f"cannot coerce {type(value).__name__} to boolean")


_COERCE_CALLABLES: dict[CoerceToType, Callable[[object], object]] = {
    CoerceToType.STRING: _coerce_string,
    CoerceToType.INTEGER: _coerce_integer,
    CoerceToType.NUMBER: _coerce_number,
    CoerceToType.BOOLEAN: _coerce_boolean,
}


# ---------------------------------------------------------------------------
# Transform builders — each returns a TransformFn closed over its arguments.
# ---------------------------------------------------------------------------


def _build_wrap_in_array(property_key: str) -> TransformFn:
    def transform(details: dict) -> dict | None:
        value = details.get(property_key)
        if isinstance(value, list):
            return None  # already correct shape
        result = copy.deepcopy(details)
        result[property_key] = [value]
        return result

    return transform


def _build_unwrap_single_array(property_key: str) -> TransformFn:
    def transform(details: dict) -> dict | None:
        value = details.get(property_key)
        if not isinstance(value, list) or len(value) != 1:
            return None  # not a single-element list — skip
        result = copy.deepcopy(details)
        result[property_key] = value[0]
        return result

    return transform


def _build_coerce_type(property_key: str, to_type: CoerceToType) -> TransformFn:
    coerce = _COERCE_CALLABLES[to_type]

    def transform(details: dict) -> dict | None:
        value = details.get(property_key)
        try:
            coerced = coerce(value)
        except (ValueError, TypeError) as exc:
            logger.warning("Cannot coerce %r to %s: %s", value, to_type.value, exc)
            return None
        if coerced == value and type(coerced) is type(value):
            return None  # already the right type and value — skip
        result = copy.deepcopy(details)
        result[property_key] = coerced
        return result

    return transform


def _build_set_value(property_key: str, literal_value: object) -> TransformFn:
    def transform(details: dict) -> dict | None:
        if details.get(property_key) == literal_value:
            return None  # already at target value — skip
        result = copy.deepcopy(details)
        result[property_key] = literal_value
        return result

    return transform


def _build_rename_key(old_key: str, new_key: str) -> TransformFn:
    def transform(details: dict) -> dict | None:
        if new_key in details:
            return None  # destination already present — skip to avoid overwrite
        if old_key not in details:
            return None  # source absent — nothing to rename
        result = copy.deepcopy(details)
        result[new_key] = result.pop(old_key)
        return result

    return transform


def _build_delete_key(property_key: str) -> TransformFn:
    def transform(details: dict) -> dict | None:
        if property_key not in details:
            return None  # already absent — skip
        result = copy.deepcopy(details)
        del result[property_key]
        return result

    return transform


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(TenantCommandMixin, BaseCommand):
    help = (
        "Repair EventDetails records by applying a data transform to a specific "
        "event_details property, WITHOUT generating revision records. "
        "Dry-runs by default — pass --apply to write changes."
    )

    def add_arguments(self, parser) -> None:
        # --- selection ---
        parser.add_argument(
            "--event-type",
            dest="event_types",
            action="append",
            metavar="VALUE",
            help="Filter to events of this event type value (repeatable).",
        )
        parser.add_argument(
            "--event-id",
            dest="event_ids",
            action="append",
            metavar="UUID",
            help="Filter to this specific event UUID (repeatable).",
        )
        parser.add_argument(
            "--event-ids-file",
            dest="event_ids_file",
            metavar="PATH",
            help="Path to a file containing one event UUID per line.",
        )

        # --- transform target ---
        parser.add_argument(
            "--property",
            required=True,
            metavar="KEY",
            help="The event_details property key to operate on.",
        )
        parser.add_argument(
            "--transform",
            required=True,
            choices=[t.value for t in Transform],
            help="Transform to apply.",
        )

        # --- per-transform extra args ---
        parser.add_argument(
            "--to-type",
            dest="to_type",
            choices=[t.value for t in CoerceToType],
            help="Target type for coerce-type transform.",
        )
        parser.add_argument(
            "--value",
            dest="literal_value",
            metavar="JSON",
            help="Literal value for set-value transform (parsed as JSON, fallback to raw string).",
        )
        parser.add_argument(
            "--new-property",
            dest="new_property",
            metavar="KEY",
            help="Destination key for rename-key transform.",
        )

        # --- execution ---
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write changes to the database. Without this flag the command is a dry run.",
        )
        parser.add_argument(
            "--sample",
            type=int,
            default=5,
            metavar="N",
            help="Number of before/after samples to print in dry-run mode (default: 5).",
        )

    def handle(self, *args, **options) -> None:
        event_types: list[str] | None = options["event_types"]
        event_ids: list[str] | None = options["event_ids"]
        event_ids_file: str | None = options["event_ids_file"]
        property_key: str = options["property"]
        transform_name: str = options["transform"]
        apply: bool = options["apply"]
        sample_count: int = options["sample"]

        # --- validate scope ---
        if not event_types and not event_ids and not event_ids_file:
            raise CommandError(
                "At least one of --event-type, --event-id, or --event-ids-file must be supplied. "
                "Refusing to run completely unscoped."
            )

        # --- build transform function ---
        transform_fn = self._build_transform(options, property_key, transform_name)

        # --- collect explicit event UUIDs ---
        explicit_event_ids: set[uuid.UUID] = set()
        if event_ids:
            for raw in event_ids:
                try:
                    explicit_event_ids.add(uuid.UUID(raw))
                except ValueError:
                    raise CommandError(f"Invalid event UUID: {raw!r}")
        if event_ids_file:
            explicit_event_ids.update(self._load_ids_from_file(event_ids_file))

        # --- build queryset ---
        qs = EventDetails.objects.select_related("event__event_type")
        if event_types:
            qs = qs.filter(event__event_type__value__in=event_types)
        if explicit_event_ids:
            qs = qs.filter(event_id__in=explicit_event_ids)
        # Coarse key-presence filter when the DB supports it; fine-grained
        # shape check is done per-record in Python below.
        qs = qs.filter(**{f"data__{EVENT_DETAILS_KEY}__{property_key}__isnull": False})

        # --- iterate and classify ---
        scanned = 0
        malformed = 0
        skipped_shape = 0  # already correct — no-op for this record
        skipped_bad_data = 0  # None data, missing event_details key, etc.
        samples: list[tuple[uuid.UUID, object, object]] = []

        pending: list[tuple[EventDetails, dict]] = []  # (instance, new_data)

        for ed in qs.iterator():
            scanned += 1

            inner = self._extract_inner_details(ed)
            if inner is None:
                skipped_bad_data += 1
                logger.debug("EventDetails pk=%s has no usable event_details — skipping.", ed.pk)
                continue

            if property_key not in inner:
                skipped_bad_data += 1
                logger.debug("EventDetails pk=%s missing property %r — skipping.", ed.pk, property_key)
                continue

            new_inner = transform_fn(inner)
            if new_inner is None:
                skipped_shape += 1
                logger.debug("EventDetails pk=%s already in correct shape — skipping.", ed.pk)
                continue

            malformed += 1
            new_data = copy.deepcopy(ed.data)
            new_data[EVENT_DETAILS_KEY] = new_inner

            if len(samples) < sample_count:
                samples.append((ed.pk, inner.get(property_key), new_inner.get(property_key)))

            pending.append((ed, new_data))

        # --- report ---
        mode_label = "APPLY" if apply else "DRY RUN"
        self.stdout.write(self.style.NOTICE(f"\n[{mode_label}] Transform: {transform_name} | Property: {property_key}"))
        self.stdout.write(f"  Records scanned      : {scanned}")
        self.stdout.write(f"  Needs change         : {malformed}")
        self.stdout.write(f"  Already correct      : {skipped_shape}")
        self.stdout.write(f"  Skipped (bad data)   : {skipped_bad_data}")

        if samples:
            self.stdout.write(self.style.NOTICE(f"\n  Sample before/after (up to {sample_count}):"))
            for pk, before, after in samples:
                self.stdout.write(f"    pk={pk}")
                self.stdout.write(f"      before : {before!r}")
                self.stdout.write(f"      after  : {after!r}")

        if not apply:
            self.stdout.write(self.style.WARNING("\n  Dry run — no changes written. Pass --apply to persist."))
            return

        # --- apply ---
        written = 0
        with transaction.atomic():
            for ed, new_data in pending:
                # Use queryset.update() to bypass the post_save signal and
                # therefore avoid generating an EventDetailsRevision record.
                EventDetails.objects.filter(pk=ed.pk).update(data=new_data)
                written += 1
                logger.info("Updated EventDetails pk=%s (no revision created).", ed.pk)

        self.stdout.write(self.style.SUCCESS(f"\n  Applied changes to {written} EventDetails record(s)."))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_transform(self, options: dict, property_key: str, transform_name: str) -> TransformFn:
        t = Transform(transform_name)

        if t is Transform.WRAP_IN_ARRAY:
            return _build_wrap_in_array(property_key)

        if t is Transform.UNWRAP_SINGLE_ARRAY:
            return _build_unwrap_single_array(property_key)

        if t is Transform.COERCE_TYPE:
            if not options.get("to_type"):
                raise CommandError("--to-type is required for the coerce-type transform.")
            return _build_coerce_type(property_key, CoerceToType(options["to_type"]))

        if t is Transform.SET_VALUE:
            if options.get("literal_value") is None:
                raise CommandError("--value is required for the set-value transform.")
            parsed = self._parse_json_value(options["literal_value"])
            return _build_set_value(property_key, parsed)

        if t is Transform.RENAME_KEY:
            if not options.get("new_property"):
                raise CommandError("--new-property is required for the rename-key transform.")
            return _build_rename_key(property_key, options["new_property"])

        if t is Transform.DELETE_KEY:
            return _build_delete_key(property_key)

        raise CommandError(f"Unknown transform: {transform_name!r}")  # pragma: no cover

    @staticmethod
    def _extract_inner_details(ed: EventDetails) -> dict | None:
        """Return the inner event_details dict, or None if the record is unusable."""
        if ed.data is None:
            return None
        inner = ed.data.get(EVENT_DETAILS_KEY)
        if not isinstance(inner, dict):
            return None
        return inner

    @staticmethod
    def _parse_json_value(raw: str) -> object:
        """Parse a raw string as JSON; fall back to returning it as a plain string."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    @staticmethod
    def _load_ids_from_file(path: str) -> set[uuid.UUID]:
        ids: set[uuid.UUID] = set()
        try:
            with open(path) as fh:
                for line_no, line in enumerate(fh, start=1):
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        ids.add(uuid.UUID(raw))
                    except ValueError:
                        raise CommandError(f"Invalid UUID on line {line_no} of {path!r}: {raw!r}")
        except OSError as exc:
            raise CommandError(f"Cannot read --event-ids-file {path!r}: {exc}")
        return ids
