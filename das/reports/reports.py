import html
import logging
import platform
from datetime import timedelta

import pandas as pd

from django.db.models import Prefetch
from django.utils import timezone
from django.utils.html import escape

import utils.schema_utils as schema_utils
from activity.models import Event, EventType
from choices.models import Choice
from observations.models import Subject
from reports.accumulator import accumulator, broadcast
from utils.memoize import memoize

logger = logging.getLogger(__name__)

HWC_EVENT_CATEGORIES = ("lewa_hwc", "hwc")
CONSERVANCY_CHOICE_LISTS = (
    "conservancy",
    "diseasemonitoring_conservancy",
    "hwcthreat_conservancy",
    "injuredabandonedanimal_conservancy",
    "lewa_conservancy",
    "postmortem_conservancy",
    "rhinobirth_conservancy",
    "vehiclerequestandfeedback_conservancy",
    "vehiclerequest_conservancy_name",
    "vehiclerequestfeedback_conservancy_name",
    "wildfire_conservancy",
)
RHINO_SIGHTINGS_EVENT_TYPES = (
    "black_rhino_sighting",
    "black_rhino_two",
    "white_rhino_sighting",
    "black_rhino_sighting_rv002",
    "white_rhino_sighting_rv002",
)


@memoize
def get_rendered_schema_properties(event_type):
    props, _ = schema_utils.get_all_fields_and_definitions(event_type.schema)
    return props


@memoize
def get_hwc_event_types(_):
    return [et.value for et in EventType.objects.filter(category__value__in=HWC_EVENT_CATEGORIES)]


@memoize
def get_rainfall_event_types(_):
    rainfall_categories = ("lewa_monitoring", "monitoring")
    return [
        et.value for et in EventType.objects.filter(category__value__in=rainfall_categories) if "rainfall" in et.value
    ]


def get_event_details(event):
    event_details = event.event_details.all().order_by("-created_at").first()
    if event_details:
        return event_details.data["event_details"]
    return {}


@memoize
def get_choices(field):
    return {c.value: c.display for c in Choice.objects.get_choices(model=Choice.Field_Reports, field=field)}


@memoize
def get_dynamic_choices(field):
    field_details = dict(field=field, type="names")
    choices = schema_utils._get_dynamic_choices(field_details)
    return choices


EVENT_TYPE_SPECIES_MAP = {
    "gerenuk": "Gerenuk",
    "cheetah": "Cheetah",
    "giraffe": "Giraffe",
    "lion": "Lion",
    "elephant": "Elephant",
    "rhino": "Rhino",
    "buffalo": "Buffalo",
    "zebra": "Zebra",
    "hyena": "Hyena",
    "wild_dog": "Wild Dog",
    "impala": "Impala",
    "hirola": "Hirola",
    "turtle": "Turtle",
    "vulture": "Vulture",
}


def get_species_from_event_type(event_type):
    return next((v for k, v in EVENT_TYPE_SPECIES_MAP.items() if k in event_type.value), None)


def safe_get_choice_from_schema(rendered_properties, event_details, property_name, default=None):
    try:
        prop = rendered_properties[property_name]
        val = event_details[property_name]
        if isinstance(val, dict):
            # With the old choice tables, we stored a dict of "name", "value"
            # pairs
            val = val["value"]
        if isinstance(val, str):
            return escape(prop["enumNames"][val])
    except (KeyError, TypeError):
        pass
    return default


def safe_get_choice(val, key, choice_field, default=None, is_dynamic=False):
    if is_dynamic:
        choices = get_dynamic_choices(choice_field)
    else:
        choices = get_choices(choice_field)

    try:
        val = val[key]
        if isinstance(val, dict):
            # With the old choice tables, we stored a dict of "name", "value"
            # pairs
            val = val["value"]
        if isinstance(val, str):
            return escape(choices[val])
    except (KeyError, TypeError):
        pass
    return default


def _listify(o):
    if o is None:
        return []
    if isinstance(o, (dict, str)):
        return [
            o,
        ]
    if isinstance(o, list):
        return o
    return []


EVENT_LIST_TIMESTAMP_FORMAT = "%-d-%b %H:%M" if platform.system().lower() != "windows" else "%#d-%b %H:%M"


def get_permitted_events(start=None, end=None, event_categories=None):
    if not event_categories:
        return Event.objects.none()

    queryset = Event.objects.filter(event_type__category__in=event_categories).filter(event_time__range=[start, end])
    return queryset


def get_events(start=None, end=None, event_categories=None):
    events = (
        get_permitted_events(start=start, end=end, event_categories=event_categories)
        .prefetch_related("event_type", "reported_by")
        .prefetch_related(Prefetch("event_type__category"))
        .order_by("event_time")
    )
    return events


def get_conservancies():
    return get_choices("conservancy")


def get_rhino_sightings(start=None, end=None, event_categories=None):
    events = get_permitted_events(start=start, end=end, event_categories=event_categories).filter(
        event_type__value__in=RHINO_SIGHTINGS_EVENT_TYPES
    )
    return events


def get_rhinos():
    rhinos = Subject.objects.filter(subject_subtype="rhino", is_active=True)
    return rhinos


def get_daily_report_data(since, before, event_categories=None, **kwargs):
    """
    This applies brute-force the the events, marching through the various sections of a Sit Rep and filling in the
    blanks.
    :param kwargs:
    :return:
    """
    generated_at = timezone.now()

    render_schema = schema_utils.get_schema_renderer_method()

    # Get the events we're interested in. We just need this list once and we'll run it through a set of
    # accumulotors that take whatever they need to hydrate the sit-rep
    # report.
    events = get_events(start=since, end=before, event_categories=event_categories)

    CONSERVANCY_UNSPECIFIED = "&lt;unspecified&gt;"

    def get_conservancy(event, event_details=None):
        if not event_details:
            event_details = get_event_details(event)
        if event_details:
            rendered_schema = get_rendered_schema_properties(event.event_type)
            try:
                conservancy = (
                    safe_get_choice_from_schema(rendered_schema, event_details, "conservancy", default=None)
                    or safe_get_choice_from_schema(
                        rendered_schema, event_details, "rhinobirth_conservancy", default=None
                    )
                    or safe_get_choice_from_schema(
                        rendered_schema, event_details, "reportconservancy_enum", default=None
                    )
                    or safe_get_choice_from_schema(rendered_schema, event_details, "location", default=None)
                    or safe_get_choice_from_schema(
                        rendered_schema, event_details, "reportconservancy_enum", default=None
                    )
                    or safe_get_choice_from_schema(
                        rendered_schema, event_details, "reportconservancy_enum", default=None
                    )
                    or safe_get_choice_from_schema(
                        rendered_schema, event_details, "reportconservancy_enum", default=None
                    )
                )
                if conservancy:
                    return conservancy
            except Exception:
                pass
        return CONSERVANCY_UNSPECIFIED

    conservancy_census = [
        ("--Lewa--", 62, 66),
        ("Lewa", 62, 66),
        ("Borana", 21, 0),
        ("Sera", 10, 0),
        (CONSERVANCY_UNSPECIFIED, 0, 0),
    ]
    conservancy_census = dict(
        (
            k.lower(),
            {
                "conservancy": k,
                "total_rhino_black": b,
                "total_rhino_white": w,
                "denominator": {"black_rhino_sighting_rv002": b, "white_rhino_sighting_rv002": w, "total": b + w},
            },
        )
        for (k, b, w) in conservancy_census
    )

    # Convenience method to initialize a 'wildlife_sightings' block for a
    # single conservancy.
    def default_conservancy_ws(conservancy):
        c = {
            "total_sightings": 0,
            "rhino_sightings": [
                {"type": "Black Rhino", "event_type": "black_rhino_sighting_rv002", "count": 0, "percentage": 0},
                {"type": "White Rhino", "event_type": "white_rhino_sighting_rv002", "count": 0, "percentage": 0},
            ],
        }
        census = conservancy_census.get(conservancy.lower()) or conservancy_census.get(CONSERVANCY_UNSPECIFIED)
        c.update(census)
        return c

    # Accumulator for the 'Wildlife Sightings' portion of report.
    def rhino_sightings(accum, event):
        """The new rhino sightings are: black_rhino_sighting_rv002, white_rhino_sighting_rv002
        By species, age, gender and injury status.
        """
        if "rhino_sighting" not in event.event_type.value:
            return

        event_details = get_event_details(event)
        if not event_details:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        get_conservancy(event)
        event_details.get("blackrhinosighting_groupsize", 0) or event_details.get("whiterhinosighting_groupsize", 0)
        rhino_species = "Black Rhino" if "black" in event.event_type.value else "White Rhino"
        rhino_sighting_sections = {
            "sighting_details_cows": "Cow",
            "sighting_details_bulls": "Bull",
            "sighting_details_nk": "Unsexed",
        }

        for key, gender in rhino_sighting_sections.items():
            for sighting in event_details.get(key, []):
                sub_schema = rendered_schema[key]["items"]["properties"]
                age = (
                    safe_get_choice_from_schema(sub_schema, sighting, "age")
                    or safe_get_choice_from_schema(sub_schema, sighting, "known_age_cow")
                    or safe_get_choice_from_schema(sub_schema, sighting, "known_age_bull", "unspecified")
                )
                summary = dict(
                    species=rhino_species,
                    age=age,
                    gender=gender,
                    injuries=safe_get_choice_from_schema(sub_schema, sighting, "injuries", "unspecified"),
                )
                accum.loc[len(accum)] = summary

    RHINO_SIGHTINGS_COLUMNS = ["species", "age", "gender", "injuries"]
    rhino_sightings = accumulator(pd.DataFrame(columns=RHINO_SIGHTINGS_COLUMNS), rhino_sightings)

    # Accumulator for 'Rhino Births'
    def rhino_births(accum, event):
        if not event.event_type.value.startswith("rhino_birth"):
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        conservancy = get_conservancy(event)
        ed = get_event_details(event)
        if not ed:
            return

        new_birth = {
            "conservancy": conservancy,
            "color": safe_get_choice_from_schema(rendered_schema, ed, "color", "unspecified"),
            "mother": safe_get_choice_from_schema(rendered_schema, ed, "femaleRhinos", "unspecified"),
            "health": safe_get_choice_from_schema(rendered_schema, ed, "health", "unspecified"),
            "station": safe_get_choice_from_schema(rendered_schema, ed, "station", "unspecified"),
        }
        accum.append(new_birth)

    rhino_births = accumulator([], rhino_births)

    def rhino_mortality(accum, event):
        eventtype_value = event.event_type.value
        if "rhino_mortality" not in eventtype_value:
            return

        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        conservancy = get_conservancy(event, ed)
        reportsource = safe_get_choice_from_schema(rendered_schema, ed, "reportsource", "unspecified")

        accum.append(
            {
                "reportsource": reportsource,
                "conservancy": conservancy,
                "rhino_name": safe_get_choice_from_schema(rendered_schema, ed, "rhino_name", "unspecified"),
                "carcass_age": safe_get_choice_from_schema(rendered_schema, ed, "carcass_age", "unspecified"),
                "cause_of_death": safe_get_choice_from_schema(rendered_schema, ed, "cause_of_death", "unspecified"),
            }
        )

    rhino_mortality = accumulator([], rhino_mortality)

    # Accumulaotor for 'Rhino territorial movement'
    def rhino_territorial_movement(accum, event):
        if event.event_type.value != "rhino_territorial_movement":
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        conservancy = get_conservancy(event)
        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)

        rhino_names = ", ".join(
            [
                safe_get_choice_from_schema(rendered_schema, dict(rhino=_), "rhino", "unspecified")
                for _ in _listify(ed.get("rhino"))
            ]
        )
        accum.append(
            {
                "conservancy": conservancy,
                "color": safe_get_choice_from_schema(rendered_schema, ed, "color", "unspecified"),
                "rhinos": escape(rhino_names),
                "health": safe_get_choice_from_schema(rendered_schema, ed, "health", "unspecified"),
                "station": safe_get_choice_from_schema(rendered_schema, ed, "station", "unspecified"),
                "behavior": safe_get_choice_from_schema(rendered_schema, ed, "behavior", "unspecified"),
            }
        )

    rhino_territorial_movement = accumulator([], rhino_territorial_movement)

    # Accumulator for 'other wildlife sightings' per Conservancy
    def other_wildlife_sightings(accum, event):
        eventtype_value = event.event_type.value
        eventtype_category_value = event.event_type.category.value

        if eventtype_category_value not in ("coast", "hirola", "field_ranger", "lewa_monitoring"):
            return
        if eventtype_value not in ("spotted_hyena_fr") and "sighting" not in eventtype_value:
            return

        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        sighting_details = ed.get("sightingDetails", None) or (ed,)
        for sighting in sighting_details:
            # sub_schema = rendered_schema["mortality_details"]["items"]["properties"]
            conservancy = get_conservancy(event, sighting)
            conservancy = accum.setdefault(
                conservancy.lower(), {"conservancy": conservancy, "total_sightings": 0, "sightings": []}
            )

            species = (
                get_species_from_event_type(event.event_type)
                or safe_get_choice_from_schema(rendered_schema, sighting, "species", None)
                or safe_get_choice_from_schema(rendered_schema, sighting, "wildlifesighting_species", None)
                or safe_get_choice(sighting, "wildlifesighting_species", "wildlifesighting_species", None)
            )
            if not species:
                return
            number_of_animals = sighting.get("numberAnimals", 0) or sighting.get(
                "wildlifesighting_totalnumberofanimals", 0
            )
            conservancy["total_sightings"] += number_of_animals

            for s in conservancy["sightings"]:
                if s["species"] == species:
                    s["count"] += number_of_animals
                    break
            else:
                conservancy["sightings"].append({"species": species, "count": number_of_animals})

    other_wildlife_sightings = accumulator({}, other_wildlife_sightings)

    def carcass(accum, event):
        eventtype_value = event.event_type.value
        if eventtype_value not in ("loss_of_animal_life", "carcass") and "mortality" not in eventtype_value:
            return
        if "rhino" in eventtype_value:
            return

        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        conservancy = get_conservancy(event, ed)
        section_area = safe_get_choice_from_schema(rendered_schema, ed, "sectionarea", "unspecified")
        cause_of_death = safe_get_choice_from_schema(rendered_schema, ed, "cause_of_death", "unspecified")
        for mortality in _listify(ed.get("mortality_details")):
            sub_schema = rendered_schema["mortality_details"]["items"]["properties"]
            accum.append(
                {
                    "conservancy": conservancy,
                    "species": safe_get_choice_from_schema(sub_schema, mortality, "species", "unspecified"),
                    "cause_of_death": cause_of_death,
                    "section_area": section_area,
                    "number_animals": mortality.get("species_no", 0),
                }
            )

    carcass = accumulator([], carcass)

    # Accumulator for 'movement through gaps'
    def gap_movement(accum, event):
        if event.event_type.value != "wildlife_gap_movement":
            return

        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        gap = safe_get_choice_from_schema(rendered_schema, ed, "wildlifeGap", None)
        species = safe_get_choice_from_schema(rendered_schema, ed, "species", "unspecified")
        if not gap:
            return

        for sum in accum:
            if sum["gap_name"] == gap and sum["species"] == species:
                sum["total_in"] += ed.get("number_in", 0)
                sum["total_out"] += ed.get("number_out", 0)
                break
        else:
            accum.append(
                {
                    "gap_name": gap,
                    "species": species,
                    "total_in": ed.get("number_in", 0),
                    "total_out": ed.get("number_out", 0),
                }
            )

    gap_movement = accumulator([], gap_movement)

    # Accumulator for 'Rainfall'
    def rainfall(accum, event):
        if event.event_type.value not in get_rainfall_event_types(None):
            return

        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        conservancy = safe_get_choice_from_schema(rendered_schema, ed, "conservancy", "unspecified")
        station = ed.get("rainfallreport_stationlocation") or safe_get_choice_from_schema(
            rendered_schema, ed, "station", "unspecified"
        )
        mm = ed.get("number_rainfall", 0) or ed.get("rainfallreport_rainfallmm", 0)

        c = accum.setdefault(conservancy, {"conservancy": conservancy, "rainfall": []})

        for sum in c["rainfall"]:
            if sum["station"] == station:
                sum["total_mm"] += mm
                break
        else:
            c["rainfall"].append({"station": station, "total_mm": mm})

    rainfall = accumulator({}, rainfall)

    # Accumulator for 'fence breakage'
    def fence_breakage(accum, event):
        if event.event_type.value != "fence_breakage":
            return
        ed = get_event_details(event)
        if not ed:
            return

        rendered_schema = get_rendered_schema_properties(event.event_type)
        etime = event.event_time.astimezone(timezone.get_current_timezone())
        b = {
            "time": etime.strftime(EVENT_LIST_TIMESTAMP_FORMAT),
            "section": safe_get_choice_from_schema(rendered_schema, ed, "fenceSection", "unspecified"),
            "species": safe_get_choice_from_schema(rendered_schema, ed, "species", "unspecified"),
            "animal_name": safe_get_choice_from_schema(rendered_schema, ed, "animal_name", "unspecified"),
            "reported_by": safe_get_choice_from_schema(rendered_schema, ed, "reported_by", "unspecified"),
            "action": safe_get_choice_from_schema(rendered_schema, ed, "actionTaken", "unspecified"),
            "feedback": escape(ed.get("feedback", "")),
        }

        accum.append(b)

    fence_breakage = accumulator([], fence_breakage)

    # Accumulator for an event category
    def make_events_accum(categories):
        event_categories = categories

        def inner_events(accum, event):
            if event.event_type.category.value not in event_categories:
                return

            # Special case: exclude human_wildlife_conflict events which are to be included in another section of
            #               this report.
            if event.event_type.value in get_hwc_event_types(None):
                return

            event_details = schema_utils.generate_details(event, render_schema(event.event_type.schema))
            en = event.notes.all().order_by("created_at")

            def build_note(note):
                return {
                    "text": html.escape(note.text),
                    "username": note.created_by_user.username,
                    "created_at": note.created_at.astimezone(timezone.get_current_timezone()).strftime(
                        EVENT_LIST_TIMESTAMP_FORMAT
                    ),
                }

            accum.append(
                {
                    "title": "{}: {}".format(event.serial_number, escape(event.title)),
                    "event_name": "{}: {}".format(event.serial_number, escape(event.title)),
                    "event_time": event.event_time.astimezone(timezone.get_current_timezone()).strftime(
                        EVENT_LIST_TIMESTAMP_FORMAT
                    ),
                    "attributes": sorted(event_details, key=lambda x: x["order"]),
                    "notes": [build_note(n) for n in en],
                }
            )

        return inner_events

    security_events = accumulator([], make_events_accum(("lewa_security", "security", "security_new")))
    security_ke_police_events = accumulator([], make_events_accum(("security_ke_police",)))
    findrep_events = accumulator([], make_events_accum(("findrep_category",)))

    # Accumulator for 'human wildlife conflict'
    def human_wildlife_conflict(accum, event):
        if event.event_type.value not in get_hwc_event_types(None):
            return

        event_details = schema_utils.generate_details(event, render_schema(event.event_type.schema))

        en = event.notes.all().order_by("created_at")

        def build_note(note):
            return {
                "text": html.escape(note.text),
                "username": note.created_by_user.username,
                "created_at": note.created_at.astimezone(timezone.get_current_timezone()).strftime(
                    EVENT_LIST_TIMESTAMP_FORMAT
                ),
            }

        accum.append(
            {
                "title": "{}: {}".format(event.serial_number, escape(event.title)),
                "event_name": "{}: {}".format(event.serial_number, escape(event.title)),
                "event_time": event.event_time.astimezone(timezone.get_current_timezone()).strftime(
                    EVENT_LIST_TIMESTAMP_FORMAT
                ),
                "attributes": sorted(event_details, key=lambda x: x["order"]),
                "notes": [build_note(n) for n in en],
            }
        )

    human_wildlife_conflict = accumulator([], human_wildlife_conflict)
    b = broadcast(
        (
            rhino_sightings,
            rhino_births,
            rhino_territorial_movement,
            rhino_mortality,
            other_wildlife_sightings,
            carcass,
            gap_movement,
            rainfall,
            fence_breakage,
            security_events,
            security_ke_police_events,
            findrep_events,
            human_wildlife_conflict,
        )
    )

    for event in events:
        b.send(event)

    rhino_births = rhino_births.send(None)
    rhino_territorial_movement = rhino_territorial_movement.send(None)
    rhino_mortality = rhino_mortality.send(None)
    other_wildlife_sightings = other_wildlife_sightings.send(None)
    carcass = carcass.send(None)
    gap_movement = gap_movement.send(None)
    rainfall = rainfall.send(None)
    fence_breakage = fence_breakage.send(None)
    rhino_sightings = rhino_sightings.send(None)
    security_events = security_events.send(None)
    security_ke_police_events = security_ke_police_events.send(None)
    findrep_events = findrep_events.send(None)
    human_wildlife_conflict = human_wildlife_conflict.send(None)

    #
    # Query for rhino sightings over the last 7 days, to determine which rhinos are 'missing' for
    # an inordinate time.
    #
    near_threshold = before - timedelta(days=3)
    far_threshold = before - timedelta(days=7)
    rhino_sighting_events = get_rhino_sightings(far_threshold, before, event_categories=event_categories)
    missing_rhinos = dict((str(r.id), {"name": escape(r.name), "days_ago": 1000000}) for r in get_rhinos())

    for event in rhino_sighting_events:
        ed = get_event_details(event)
        if not ed:
            continue

        rhino_sighting_sections = ("sighting_details_cows", "sighting_details_bulls", "sighting_details_nk")

        if any(True for key in event_details.keys() if key in rhino_sighting_sections):
            for key in rhino_sighting_sections:
                if key in event_details:
                    for sighting in event_details[key]:
                        rhinos_in_event = _listify(sighting.get("rhino"))
                        rhino_ids_in_event = [_.get("value") if isinstance(_, dict) else _ for _ in rhinos_in_event]
        else:
            rhinos_in_event = _listify(ed.get("blackRhinos")) + _listify(ed.get("whiteRhinos"))
            rhino_ids_in_event = [_.get("value") if isinstance(_, dict) else _ for _ in rhinos_in_event]

        for rhino_id in rhino_ids_in_event:
            if rhino_id:
                if event.event_time > near_threshold:
                    missing_rhinos.pop(rhino_id, None)
                else:
                    # Use Math.ceil(timedelta) to indicate 'days ago'. Ex.
                    # 3 days 5 hours => 4 days ago.
                    missing_rhinos[rhino_id]["days_ago"] = min(
                        missing_rhinos[rhino_id]["days_ago"], (before - event.event_time).days + 1
                    )

    # Post-process missing rhinos.
    missing_rhinos = sorted(missing_rhinos.values(), key=lambda _: _["days_ago"], reverse=True)
    for r in missing_rhinos:
        r["days_ago"] = "> 7" if r["days_ago"] > 7 else str(r["days_ago"])

    REPORT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %Z"
    REPORT_TIME_FORMAT = "%-d %B %Y %Z" if platform.system().lower() != "windows" else "%#d %B %Y %Z"
    since_text = since.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
    before_text = before.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIMESTAMP_FORMAT)
    context = {
        "report_filename": "Daily-SitRep-{}.docx".format(
            before.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d")
        ),
        "report_time": before.astimezone(timezone.get_current_timezone()).strftime(REPORT_TIME_FORMAT),
        "report_daterange_text": "Including events from: {} to: {}".format(since_text, before_text),
        "footer_text": "Report generated by EarthRanger user {username} at {generated_at}".format(
            generated_at=generated_at.strftime(REPORT_TIMESTAMP_FORMAT), username=kwargs.get("username") or "system"
        ),
        "rhino_births": rhino_births,
        "rhino_mortality": rhino_mortality,
        "missing_rhinos": missing_rhinos,
        "rhino_sightings": rhino_sightings.groupby(RHINO_SIGHTINGS_COLUMNS)
        .size()
        .reset_index(name="count")
        .to_dict(orient="records"),
        "rhino_territorial_movement": rhino_territorial_movement,
        "other_sightings": other_wildlife_sightings.values(),
        "carcass": carcass,
        "gap_movement": gap_movement,
        "rainfall": rainfall.values(),
        "fence_breakage": fence_breakage,
        "security_events": security_events,
        "security_ke_police_events": security_ke_police_events,
        "findrep_events": findrep_events,
        "human_wildlife_conflict": human_wildlife_conflict,
    }

    return context
