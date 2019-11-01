# import logging
# from django.core.management.base import BaseCommand
# from django.contrib.staticfiles import finders

# from activity.models import Event, EventType
# from activity.models import EventType
# from utils import schema_utils


# logger = logging.getLogger(__name__)


# class Command(BaseCommand):

#     help = 'Validate presence of event marker images.'

#     def handle(self, *args, **options):

#         render_f = schema_utils.get_schema_renderer_method()
#         schema_accumulator = {}
#         for et in EventType.objects.all():
#             schema_accumulator[et.value] = render_f(et.schema)

#         lines = []
#         lines.append('create materialized view event_details_view as select ')
#         lines.append(' ed.event_id, et.display as "event_type", ')

#         fieldset = set()
#         for a, b in generate_field_details(schema_accumulator):
#             path = ','.join(a)
#             fielddef = f'(data#>>\'{{{path}}}\')::{b} as "{a[1]}"'
#             fieldset.add(fielddef)
#         lines.append(',\n'.join(fieldset))
#         lines.append(' from activity_eventdetails ed ')
#         lines.append(' join activity_event e on e.id = ed.event_id ')
#         lines.append(' join activity_eventtype et on et.id = e.event_type_id ')

#         for line in lines:
#             print(line)


# def generate_propkey_suffix():
#     used_keys = {}

#     k = yield ''

#     while True:
#         suf = used_keys.setdefault(k, {'val': 0})

#         if suf['val'] == 0:
#             k = yield ''
#         else:
#             k = yield f"_{suf['val']}"

#         suf['val'] = suf['val'] + 1


# def generate_field_details(schema_accumulator):
#     used_properties = set()
#     suffix_generator = generate_propkey_suffix()
#     next(suffix_generator)

#     for k, v in schema_accumulator.items():
#         properties = v['schema']['properties']

#         for propkey, propval in properties.items():

#             proptype = propval.get('type', '')
#             prophash = f'{propkey}:{proptype}'
#             if prophash in used_properties:
#                 continue
#             used_properties.add(prophash)

#             suf = suffix_generator.send(propkey)
#             propkey = f"{propkey}{suf}"
#             if propval.get('enum'):
#                 if propval.get('type') == 'string':
#                     yield ('ed.event_details', propkey, 'name'), 'TEXT'

#             elif propval.get('type') == 'string':
#                 yield ('ed.event_details', propkey), 'TEXT'

#             elif propval.get('type') == 'number':
#                 yield ('ed.event_details', propkey), 'NUMERIC'
