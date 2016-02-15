from django.db import transaction
from django.test import TestCase

from activity.models import Event, EventAttachment
from activity.models import get_sentinel_user


class TestSourcePlugin(TestCase):
    def setUp(self):
        pass

    def test_sentinel_user(self):
        user = get_sentinel_user()
        self.assertEqual('deleted', user.username)

    def test_create_event_with_attachment(self):
        with transaction.atomic():
            e = Event.objects.create(name='Bogus event', description=fake_long_description,
                                     provenance=Event.INFORMANT,
                                     event_type=Event.ET_LIVESTOCK_THEFT,
                                     priority='urgent',
                                     attributes={},
                                     )

        self.assertIsNotNone(e.id)

fake_long_description = '''
Lorem ipsum dolor sit amet, duis libero nunc vitae wisi et, etiam viverra hic sagittis aliquam adipiscing,
orci neque vitae blandit arcu, ut vulputate gravida placerat tellus iaculis bibendum, quis et ante. Vivamus
nunc justo suscipit amet, praesent purus vestibulum tristique mauris sem platea, eu in ultricies diam diam
gravida, quis metus arcu id magna tempor aliquam. Sagittis pellentesque, feugiat porttitor aliquam vestibulum
pellentesque, lacus ornare nec velit. Pulvinar orci mattis gravida, urna quisque vivamus purus vel elit, at
commodo et aenean dapibus, eros sit sed nec, turpis risus eros eleifend maxime morbi. Magna magna est, eleifend proin
velit, vivamus donec integer sodales, sed in semper hac ut libero voluptatum, aliquam velit mauris in mauris orci.
Libero aliquam lobortis torquent posuere risus nunc, rutrum sollicitudin urna, ac eu lobortis vel, tristique nisl at
tincidunt justo. Habitasse tempor erat egestas wisi et. Ipsum primis gravida at sed enim arcu, consectetuer a vestibulum
nisl ullamcorper fusce.
'''
