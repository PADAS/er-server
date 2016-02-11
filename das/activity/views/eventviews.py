from datetime import timedelta

from oauth2_provider.ext.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics

from activity.models import Event
from activity.serializers import EventSerializer

LAST_DAYS = timedelta(days=3)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

class EventsView(generics.ListCreateAPIView):
    __doc__ = """
    Returns all events.
    Optional query-params:
    bbox, where bbox is the (west, south, east, north) lon,lat pairs.
        example: bbox=14.24, .41, 15.45, 1.66
    page, page number
    page_size, (default is {page_size}, max is {max_page_size})
    """.format(page_size=StandardResultsSetPagination.page_size,
                    max_page_size=StandardResultsSetPagination.max_page_size)

    authentication_classes = ((OAuth2Authentication, SessionAuthentication))
    permission_classes = ((IsAuthenticated,))

    serializer_class = EventSerializer

    pagination_class = StandardResultsSetPagination
    queryset = Event.objects.all().order_by('-created_at')

    def get_queryset(self):
        queryset = Event.objects.all().order_by('-created_at')
        bbox = self.request.query_params.get('bbox', None)
        if bbox:
            bbox = bbox.split(',')
            bbox = [float(v) for v in bbox]
            if len(bbox) != 4:
                raise ValueError("invalid bbox param")
            queryset = Event.objects.by_bbox(bbox, last_days=LAST_DAYS).order_by('-created_at')
        return queryset

    # def get(self, request, *args, **kwargs):
    #     return super().get(request, *args, **kwargs)





class EventView(generics.RetrieveUpdateAPIView):
    serializer_class = EventSerializer
    queryset = Event.objects.all()
    lookup_field = 'id'

    def get_serializer_context(self):
        context = {}
        event = self.get_object()

        context['time'] = event.created_at
        context['coordinates'] = event.location
        context['request'] = self.request
        return context


# @api_view(['POST', 'GET'])
# @authentication_classes((OAuth2Authentication, SessionAuthentication))
# @permission_classes((IsAuthenticated,))
# def event(request, *args, **kwargs):
#     """
#     For a manufacturer_id:
#         list some observations, or create a new observation.
#     """
#     if request.method == 'POST':
#
#         try:
#             location = request.data.get('location')
#             lat = location.get('lat', None)
#             lon = location.get('lon', None)
#
#             location = Point(x=float(lon), y=float(lat))
#         except:
#             location = None
#
#         name = request.data.get('name', None)
#         event_type = request.data.get('event_type', None)
#
#         # if stuff is missing:
#         #     return Response(data="Missing parameters.",
#         #                     status=status.HTTP_400_BAD_REQUEST)
#
#
#         provenance = request.data.get('provenance', 'informant')
#         Event(name=name, provenance=provenance)
#
#         event_data = {
#             'location': location,
#             'event_type': event_type,
#             'provenance': provenance,
#             'name': name,
#         }
#
#         serializer = EventSerializer(data=event_data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#
#     elif request.method == 'GET':
#
#         event_id = kwargs.get('event_id')
#         # event_id = request.query_params.get('event_id')
#         # event_type = request.query_params.get('event_type', 'informant')
#         if event_id:
#             event = Event.objects.get(id=event_id)
#
#             if event:
#                 serializer = EventSerializer(event)
#                 return Response(serializer.data)
#
#         return Response(status=status.HTTP_404_NOT_FOUND)
