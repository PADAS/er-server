from datetime import datetime, timedelta
import pytz

from django.core.management.base import BaseCommand
from django.db.models import F
from tracking.tasks import run_plugins
from observations.models import Source
from tracking.models import SourcePlugin

class Command(BaseCommand):

    help = 'Run ingester for given Subject.'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str)

    def handle(self, *args, **options):

        ts = pytz.utc.localize(datetime.utcnow())

        for source in Source.objects.filter(subjectsource__subject__name=options['name'],
                                       subjectsource__assigned_range__contains=ts).annotate(
                assigned_range=F('subjectsource__assigned_range')).order_by('-assigned_range'):

            for sp in SourcePlugin.objects.filter(source=source):
                if sp.should_run():
                    sp.execute()
                else:
                    print('Not running for SourcePlugin: %s' % (sp,))