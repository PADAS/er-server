from django.core.management.base import BaseCommand
from activity.models import Event, EventRelationshipType, EventRelationship


class Command(BaseCommand):

    help = 'List events'

    def handle(self, *args, **options):

        EventRelationshipType.objects.get_or_create(value='contains')
        EventRelationshipType.objects.get_or_create(value='is_linked_to')

        # t = EventRelationshipType.objects.all()
        # for item in t:
        #     print(item)


        e0 = Event.objects.get(message='BRS')

        e1 = Event.objects.get(message='WRS')

        e2 = Event.objects.get(message='hello.')

        EventRelationship.objects.add_relationship(e0, e1, 'is_linked_to')

        EventRelationship.objects.add_relationship(e1, e2, 'contains')


        # EventRelationship.objects.remove_relationship(e1, e0, 'is_linked_to')
        # EventRelationship.objects.remove_relationship(e1, e0, 'contains')
        #
        # EventRelationship.objects.remove_relationship(e1, e2, 'contains')

        # er, created = EventRelationship.objects.get_or_create(from_event=e0, to_event=e1, type=EventRelationshipType.objects.get(value='contains'))
        # print((er, created))
        #
        # er, created = EventRelationship.objects.get_or_create(from_event=e1, to_event=e0, type=EventRelationshipType.objects.get(value='is_linked_to'))
        # print((er, created))
        #
        # er, created = EventRelationship.objects.get_or_create(from_event=e1, to_event=e0,
        #                                                       type=EventRelationshipType.objects.get(value='contains'))
        # print((er, created))
        #
        # er, created = EventRelationship.objects.get_or_create(from_event=e1, to_event=e2, type=EventRelationshipType.objects.get(value='is_linked_to'))
        # er, created = EventRelationship.objects.get_or_create(from_event=e2, to_event=e1, type=EventRelationshipType.objects.get(value='is_linked_to'))
        # print((er, created))
