from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from activity.models import CommunityInput
from activity.permissions import StandardModelPermissions
from activity.serializers.community_input import CommunityInputSerializer


class CommunityInputViewSet(ModelViewSet):
    serializer_class = CommunityInputSerializer
    lookup_field = "value"

    def get_queryset(self):
        qs = CommunityInput.objects.all()
        if not self.request.user.is_authenticated:
            qs = qs.filter(is_active=True)
        return qs

    def get_authenticators(self):
        action_map = getattr(self, "action_map", {})
        request = getattr(self, "request", None)
        method = request.method.lower() if request is not None else None
        if action_map.get(method) == "retrieve":
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.action == "retrieve":
            return []
        return [IsAuthenticated(), StandardModelPermissions()]
