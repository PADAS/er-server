from rest_framework.generics import ListCreateAPIView
from rest_framework.pagination import StandardResultsSetPagination

from buoy.serializers.gear import GearSerializer
from utils.drf import StandardResultsSetCursorPagination, StandardResultsSetPagination


class GearCursorPagination(StandardResultsSetCursorPagination):
    cursor_query_Param = "id"
    ordering = "recorded_at"


class GearView(ListCreateAPIView):
    serializer_class = GearSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        pass


class GearsView(ListCreateAPIView):
    serializer_class = GearSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        pass
