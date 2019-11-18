from typing import NamedTuple
import logging
import re
import csv

from django.core.management.base import BaseCommand
from django.db import transaction
from activity.models import EventCategory, EventType
from choices.models import Choice, DynamicChoice

logger = logging.getLogger(__name__)


class Model(NamedTuple):
    model_class: any
    field: str


models = [
    Model(Choice, "display"),
    Model(EventCategory, "display"),
    Model(EventType, "display"),
]


class Command(BaseCommand):

    help = 'Inplace localize'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str,
                            help="csv file with english,french pairs to translate")
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='No updates.',
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        translations = {}
        with open(options["file"], mode="r", encoding="utf-8") as fh:
            for line in csv.reader(fh):
                if not line:
                    continue
                en, display = line
                logger.info(f" en={en}, display={display}")
                translations[en.strip()] = display.strip()

        with transaction.atomic():
            self.update_simple_models(translations)
            self.update_event_types(translations)

    def update_simple_models(self, translations):
        for model in models:
            for row in model.model_class.objects.all():
                display = getattr(row, model.field)
                logger.info(f"looking up {display}")
                if display and display in translations:
                    translated_display = translations[display]
                    logger.info(f"Translate {display} to {translated_display}")
                    setattr(row, model.field, translated_display)
                    if not self.dry_run:
                        row.save()

    def update_event_types(self, translations):
        title_re = re.compile(r"\"title\":\s\"([^\"]+)\"")
        for et in EventType.objects.all():
            schema = et.schema
            match_group = 1
            start_pos = 0
            while True:
                match = title_re.search(schema, start_pos)
                if not match:
                    break
                start_pos = match.start(match_group)
                display = match.group(match_group)
                if display and display in translations:
                    translated_display = translations[display]
                    logger.info(
                        f"Translate event title {display} to {translated_display}")
                    schema = schema[:match.start(
                        match_group)] + translated_display + schema[match.end(match_group):]
            if schema != et.schema:
                logger.info(f"Updated: {et.schema}")
                if not self.dry_run:
                    et.schema = schema
                    et.save()
