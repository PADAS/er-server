from django.core.management.base import BaseCommand
from activity.models import Event, EventRelationshipType, EventRelationship


class Command(BaseCommand):

    help = 'List events'

    def handle(self, *args, **options):

        # EventRelationshipType.objects.create(value='child')
        # EventRelationshipType.objects.create(value='linked')
        #
        # t = EventRelationshipType.objects.all()
        # for item in t:
        #     print(item)


        e0 = Event.objects.get(message='BRS')
        print([x.to_event.message for x in e0.children])
        e1 = Event.objects.get(message='WRS')

        print([x.from_event.message for x in e1.parents])
        #
        # er, created = EventRelationship.objects.get_or_create(from_event=e0, to_event=e1, type=EventRelationshipType.objects.get(value='child'))
        # print((er, created))
        #
        # er, created = EventRelationship.objects.get_or_create(from_event=e1, to_event=e0,
        #                                                       type=EventRelationshipType.objects.get(value='child'))
        # print((er, created))
