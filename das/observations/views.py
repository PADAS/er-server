from django.http import HttpResponse
# from rest_framework import status
# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from observations.models import Observation
# from observations.serializers import ObservationSerializer
#
# @api_view(['GET', 'POST'])
# def observation(request, id):
#
#     try:
#         obs = Observation.objects.get(id=id)
#     except Observation.DoesNotExist:
#         return Response(status=status.HTTP_404_NOT_FOUND)
#
#     if request.method == 'GET':
#         serializer = ObservationSerializer(obs)
#         return Response(serializer.data)
