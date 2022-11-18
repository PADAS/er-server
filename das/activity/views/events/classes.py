from rest_framework.generics import ListAPIView

from activity.models import EventClass, EventClassFactor
from activity.serializers import EventClassFactorSerializer, EventClassSerializer


class EventClassFactorsView(ListAPIView):
    serializer_class = EventClassFactorSerializer

    def get_queryset(self):
        queryset = EventClassFactor.objects.all()
        queryset = queryset.order_by("eventclass__ordernum", "eventfactor__ordernum")

        return queryset


class EventClassesView(ListAPIView):
    serializer_class = EventClassSerializer
    queryset = EventClass.objects.all().order_by("ordernum")
