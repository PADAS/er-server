from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from observations.models import Observation, Source
from observations.serializers import ObservationSerializer
from oauth2_provider.ext.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.gis.geos import Point

@api_view(['POST', 'GET'])
@authentication_classes((OAuth2Authentication, SessionAuthentication))
@permission_classes((IsAuthenticated,))
def observation_list(request):
    """
    For a manufacturer_id:
        list some observations, or create a new observation.
    """
    if request.method == 'POST':

        try:
            lat = request.data.get('lat', None)
            lon = request.data.get('lon', None)

            location = Point(x=float(lon), y=float(lat))
        except:
            location = None

        manufacturer_id = request.data.get('manufacturer_id', None)
        source_type = request.data.get('source_type', None)

        if not manufacturer_id or not source_type:
            return Response(data="Missing parameters. Please provide both 'manufacturer_id' and 'source_type'.",
                            status=status.HTTP_400_BAD_REQUEST)

        src, created = Source.objects.get_or_create(source_type=source_type,
                                           manufacturer_id=manufacturer_id,
                                           defaults={'model_name':'auto-created',
                                                     'additional': {'note':'automatically created during observation post.'}})

        recorded_at = request.data.get('recorded_at')
        # if recorded_at:
        #     recorded_at = parser.parse(recorded_at)

        observation_data = {
            'location': location,
            'recorded_at': recorded_at,
            'source': src.id,
            'additional': request.data.get('additional', {"note":"default"}),
        }


        serializer = ObservationSerializer(data=observation_data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'GET':

        manufacturer_id = request.query_params.get('manufacturer_id')
        if manufacturer_id:
            src = Source.objects.filter(source_type='gps-radio', manufacturer_id=manufacturer_id).first()

            if src:

                o = Observation.objects.filter(source=src)[:5]
                serializer = ObservationSerializer(o, many=True)
                return Response(serializer.data)

        return Response(status=status.HTTP_404_NOT_FOUND)
