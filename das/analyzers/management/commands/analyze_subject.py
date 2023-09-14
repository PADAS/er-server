from datetime import datetime

from analyzers.tasks import analyze_subject_
from observations.models import Subject
from utils.tenant.commands import TenantBaseCommand


class Command(TenantBaseCommand):
    help = "Run analyzers for Subject, by name."

    def handle(self, *args, **options):
        print('Analyzer, searching for Subjects with name = "%s".' % (options["name"],))
        for sub in Subject.objects.filter(name=options["name"]):
            ostart = datetime.now()
            analyze_subject_(str(sub.id))
            print("-----> Analyzed subject %s in %d seconds." % (sub.name, (datetime.now() - ostart).total_seconds()))

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, help="Subject name.")
