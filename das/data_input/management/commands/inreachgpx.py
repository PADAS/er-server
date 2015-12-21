from django.core.management.base import BaseCommand
from optparse import make_option
from data_input.plugins import inreachgpx

class Command(BaseCommand):

    help = 'Read Inreach GPX file and add observations.'

    option_list = BaseCommand.option_list + (
        make_option('-f', '--file', action='store', type='string', dest='filename', help='Path to GPX file.' ),
        make_option('-s', '--sourceid', action='store', type='string', dest='source_id', help='UUID for source in DAS')
                    )

    def handle(self, *args, **options):

        if any(options[x] is None for x in ('filename', 'source_id')):
            self.print_help(None, __name__.split('.')[-1])
            exit()


        print(options['filename'], options['source_id'])


        inreachgpx.process_gpx_file(options['filename'], options['source_id'])
