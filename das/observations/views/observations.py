import logging

from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, get_object_or_404

from observations.models import Observation, Subject
from observations.serializers import FlattenObservationSerializer
from observations.utils import VIEW_SUBJECT_PERMS, dateparse

logger = logging.getLogger(__name__)


class FlattenObservationsView(ListAPIView):
    serializer_class = FlattenObservationSerializer

    def get_queryset(self):
        subject_id = self.request.query_params.get("subject_id")
        created_after = dateparse(
            self.request.query_params.get("created_after"))

        subject = get_object_or_404(Subject, pk=subject_id)
        if not self.request.user.has_any_perms(VIEW_SUBJECT_PERMS, subject):
            raise PermissionDenied

        queryset = Observation.objects.get_subject_observations(subject)
        queryset = queryset.by_created_after(created_after)

        return queryset.order_by("-recorded_at")
