from django.core.management.base import BaseCommand
from django.contrib.staticfiles import finders

from activity.models import Event, EventType


class Command(BaseCommand):

    help = 'Validate presence of event marker images.'

    def handle(self, *args, **options):

        for et in EventType.objects.all():

            print('Validating images for EvenType {}'.format(et.value))
            for priority, priority_name in Event.PRIORITY_CHOICES:
                for state, state_name in Event.STATE_CHOICES:
                    image = Event.marker_icon(et.value, priority, state)
                    image = image[8:]

                    print('{0} -> {1}'.format(et.value, image))
                    if not finders.find(image):
                        print('\tMissing image {0}'.format(image))
