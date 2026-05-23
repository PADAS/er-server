from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db.models import F

from analyzers.tasks import analyze_subject_
from observations.models import Subject
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, BaseCommand):
    help = "Run analyzers for all Subjects having observations within the last n minutes."

    def handle(self, *args, **options):
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(minutes=options["n"])

        print("Analyzer, selecting for range start: %s, end: %s" % (start, end))
        for sub in (
            Subject.objects.filter(
                subjectsource__source__observation__recorded_at__gte=start,
                subjectsource__source__observation__recorded_at__lte=end,
                subjectsource__assigned_range__contains=F("subjectsource__source__observation__recorded_at"),
            )
            .annotate(recorded_at=F("subjectsource__source__observation__recorded_at"))
            .order_by("name")
            .distinct("name")
        ):
            print(sub.name, sub.recorded_at)

            ostart = datetime.now()
            analyze_subject_(str(sub.id))
            print("-----> Analyzed subject %s in %d seconds." % (sub.name, (datetime.now() - ostart).total_seconds()))

    def add_arguments(self, parser):
        parser.add_argument("-n", type=int, help="minutes for selecting Subjects.", default=10)
