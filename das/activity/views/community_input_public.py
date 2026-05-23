from __future__ import annotations

import logging

import filetype

from django.db import models, transaction
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from activity.models import (
    CommunityInput,
    CommunityInputEvent,
    CommunityInputEventType,
    Event,
    EventType,
)
from activity.schemas.eventtype_service import EventTypeSchemaService
from activity.serializers.community_input import CommunityInputEventSubmissionSerializer
from activity.serializers.event_types_v2 import EventTypeV2Serializer
from activity.views.events.files import EventFilesView
from activity.views.events.notes import EventNotesView
from activity.views.events.types import IconDownloadView
from activity.views.schemas import EventSchemaView, EventTypeSchemaView
from schemas.view_mixins import DynamicSchemaDataMixin
from utils.json import DirectBrowsableAPIRenderer, DirectJSONRenderer, parse_bool
from utils.tenant import get_tenant_settings
from utils.tenant.dataclass import DEFAULT_COMMUNITY_INPUT_ALLOWED_MIME_TYPES

logger = logging.getLogger(__name__)

DEFAULT_COMMUNITY_INPUT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


_MIME_SNIFF_CATEGORIES = ("image/", "video/", "audio/")
# Office documents (.docx/.xlsx/.pptx and legacy .doc/.xls) sniff as these
# container types rather than their semantic MIME, so skip the mismatch check
# for them and trust the declared type.
_MIME_SNIFF_CONTAINERS = frozenset({"application/zip", "application/x-cfb"})


class CommunityInputScopedThrottle(ScopedRateThrottle):
    """ScopedRateThrottle that reads per-tenant rates from env_settings.

    Each public community-input view sets ``throttle_scope`` (e.g.
    ``community_input_event``); we map that to the matching
    EnvironmentSettings field. The dataclass defaults populate sensible rates
    for every tenant, so this lookup normally succeeds. If the env_setting is
    unset/empty or no tenant context is available, we return ``None`` —
    SimpleRateThrottle treats that as "no throttle" rather than raising.
    """

    SCOPE_TO_ENV_FIELD = {
        "community_input_event": "community_input_event_throttle_rate",
        "community_input_file": "community_input_file_throttle_rate",
        "community_input_note": "community_input_note_throttle_rate",
        "community_input_read": "community_input_read_throttle_rate",
    }

    def get_rate(self):
        env_field = self.SCOPE_TO_ENV_FIELD.get(self.scope or "")
        if not env_field:
            return None
        try:
            return getattr(get_tenant_settings().env_settings, env_field, None) or None
        except Exception:
            logger.warning("Failed to resolve tenant throttle rate for scope %r", self.scope, exc_info=True)
            return None


def _is_allowed_community_input_mime(content_type: str, patterns) -> bool:
    if not content_type:
        return False
    content_type = content_type.split(";", 1)[0].strip().lower()
    for pattern in patterns:
        pattern = pattern.strip().lower()
        if pattern.endswith("/*"):
            if content_type.startswith(pattern[:-1]):
                return True
        elif pattern == content_type:
            return True
    return False


def _sniff_mime(file_obj) -> str | None:
    try:
        file_obj.seek(0)
        head = file_obj.read(261)
    finally:
        file_obj.seek(0)
    kind = filetype.guess(head)
    return kind.mime.lower() if kind else None


def _validate_community_input_upload(file_obj, declared: str, allowed_patterns) -> str | None:
    """Return an error message if the upload should be rejected, else None."""
    declared = (declared or "").split(";", 1)[0].strip().lower()
    if not declared:
        return "Missing Content-Type."
    sniffed = _sniff_mime(file_obj)
    if sniffed and sniffed not in _MIME_SNIFF_CONTAINERS:
        same_category = any(
            sniffed.startswith(prefix) and declared.startswith(prefix) for prefix in _MIME_SNIFF_CATEGORIES
        )
        if sniffed != declared and not same_category:
            return f"File contents ({sniffed}) do not match declared type ({declared})."
    if not _is_allowed_community_input_mime(declared, allowed_patterns):
        return f"Unsupported file type: {declared}."
    return None


class CommunityInputMixin:
    """
    Resolves the active CommunityInput from the ``community_input_value`` URL
    kwarg and raises 404 if it does not exist or is inactive.
    """

    _community_input_obj = None

    def get_community_input(self) -> CommunityInput:
        if self._community_input_obj is None:
            value = self.kwargs["community_input_value"]
            try:
                self._community_input_obj = CommunityInput.objects.get(value=value, is_active=True)
            except CommunityInput.DoesNotExist:
                raise NotFound()
        return self._community_input_obj


class CommunityInputEventTypesViewSet(CommunityInputMixin, DynamicSchemaDataMixin, ReadOnlyModelViewSet):
    """
    Read-only, unauthenticated event types scoped to a specific community input.
    The community input value is taken from the URL path.
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_read"
    serializer_class = EventTypeV2Serializer
    filter_backends = [OrderingFilter]
    lookup_field = "value"
    lookup_url_kwarg = "eventtype_value"

    def get_queryset(self) -> models.QuerySet:
        community_input = self.get_community_input()
        return (
            community_input.event_types.exclude(geometry_type=EventType.GeometryTypesChoices.POLYGON)
            .select_related("category")
            .annotate(
                in_use=models.Exists(Event.objects.filter(event_type=models.OuterRef("id"))),
                community_input_order=models.Subquery(
                    CommunityInputEventType.objects.filter(
                        community_input=community_input,
                        event_type=models.OuterRef("pk"),
                    ).values("order")[:1]
                ),
            )
        )

    def filter_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        queryset = super().filter_queryset(queryset)
        if not self.request.query_params.get("ordering"):
            queryset = queryset.order_by("community_input_order")
        return queryset

    def get_schema_queryset(self) -> models.QuerySet:
        community_input = self.get_community_input()
        return (
            community_input.event_types.exclude(geometry_type=EventType.GeometryTypesChoices.POLYGON)
            .select_related("category")
            .annotate(
                community_input_order=models.Subquery(
                    CommunityInputEventType.objects.filter(
                        community_input=community_input,
                        event_type=models.OuterRef("pk"),
                    ).values("order")[:1]
                ),
            )
        )

    @action(
        methods=["get"],
        detail=True,
        url_path="schema",
        renderer_classes=(DirectJSONRenderer, DirectBrowsableAPIRenderer),
    )
    def retrieve_schema(self, request: Request, **kwargs) -> Response:
        """Returns the rendered schema for the specified event type."""
        event_type = self.get_object()
        if event_type.version == EventType.VersionChoices.VERSION_1:
            # NOTE: instantiating EventTypeSchemaView and calling .get() directly
            # bypasses DRF's dispatch/initial/check_permissions/check_throttles
            # cycle. That is intentional here: this endpoint is mounted under
            # the unauthenticated community-input router, and the outer viewset
            # has already gated access via get_object() (which raises 404 for
            # event types not associated with an active community input).
            # Any future permission/throttle added to EventTypeSchemaView WILL
            # be silently skipped on this path — re-implement it here if that
            # ever matters. The regression test
            # `test_v1_event_type_schema_returns_200` locks the anonymous path.
            view = EventTypeSchemaView()
            view.kwargs = {"eventtype": event_type.value}
            view.request = request
            view.args = ()
            return view.get(request)
        schema_service = EventTypeSchemaService()
        pre_render = parse_bool(request.query_params.get("pre_render", False))
        if pre_render:
            schema_result = schema_service.get_rendered_schema(event_type, request)
        else:
            schema_result = schema_service.get_raw_schema(event_type)
        if schema_result.status != "failure":
            return Response(schema_result.schema, status=status.HTTP_200_OK)
        return Response(
            {"errors": [err.to_dict() for err in schema_result.errors]},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class CommunityInputEventSchemaView(CommunityInputMixin, EventSchemaView):
    """Returns the event JSON schema for community input users (no auth required)."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_read"

    def get(self, request: Request, *args, **kwargs) -> Response:
        self.get_community_input()  # raises 404 if not found / inactive
        meta = self.metadata_class()
        data = meta.determine_metadata(request, self)
        return Response(data)


class CommunityInputEventsView(CommunityInputMixin, APIView):
    """
    Creates an event via a community input. The community input value comes from
    the URL path. Events are created with ``state="review"`` and no user attribution.
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_event"
    serializer_class = CommunityInputEventSubmissionSerializer

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault("context", {"request": self.request, "format": self.format_kwarg, "view": self})
        return self.serializer_class(*args, **kwargs)

    def post(self, request: Request, *args, **kwargs) -> Response:
        community_input = self.get_community_input()

        raw = request.data
        if isinstance(raw, list):
            new_record = [dict(r) for r in raw]
        else:
            new_record = [raw.dict() if hasattr(raw, "dict") else dict(raw)]

        if not new_record:
            return Response(
                {"detail": "No events provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_event_types = set(community_input.event_types.values_list("value", flat=True))
        batch_event_types = set()

        for record in new_record:
            event_type_value = record.get("event_type")
            if not event_type_value or event_type_value not in allowed_event_types:
                return Response(
                    {"event_type": "This event type is not associated with the specified community input."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            batch_event_types.add(event_type_value)

        if len(batch_event_types) > 1:
            msg = "All events in a batch must use the same event type associated with the specified community input."
            return Response({"event_type": msg}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            serializer = self.get_serializer(data=new_record, many=True)
            if not serializer.is_valid():
                logger.warning("Invalid Event type(s) provided %s", serializer.errors)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Force state and user attribution at save time. Even if a malicious
            # submitter put `state` or `created_by_user` in the request body,
            # they were dropped during validation (not declared in the
            # serializer) and these kwargs are the only authoritative values.
            serializer.save(created_by_user=None, state=Event.SC_REVIEW)

            for event in serializer.instance:
                CommunityInputEvent.objects.create(community_input=community_input, event=event)

            data = serializer.data
            data = data if len(new_record) > 1 else data[0]
            return Response(data, status=status.HTTP_201_CREATED)


class CommunityInputEventPermission(BasePermission):
    """
    Allows access only when the event referenced by the ``id`` URL kwarg was
    created through the community input identified by ``community_input_value``.
    """

    def has_permission(self, request, view) -> bool:
        community_input = view.get_community_input()  # Let NotFound propagate as 404
        event_id = view.kwargs.get("id")
        if event_id is None:
            return False
        return CommunityInputEvent.objects.filter(community_input=community_input, event_id=event_id).exists()


class CommunityInputEventNotesView(CommunityInputMixin, EventNotesView):
    """POST notes on events created via a community input (no auth required)."""

    http_method_names = ["post"]
    permission_classes = [CommunityInputEventPermission]
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_note"


class CommunityInputEventFilesView(CommunityInputMixin, EventFilesView):
    """POST files on events created via a community input (no auth required)."""

    http_method_names = ["post"]
    permission_classes = [CommunityInputEventPermission]
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_file"

    # Set to True after MIME validation passes so the serializer skips the
    # system-level extension allowlist (which is narrower than the per-tenant
    # MIME-type allowlist that we've already checked).
    _mime_validated: bool = False

    def get_serializer_context(self) -> dict:
        ctx = super().get_serializer_context()
        ctx["skip_extension_check"] = self._mime_validated
        return ctx

    def create(self, request: Request, *args, **kwargs) -> Response:
        file_obj = None
        if "filecontent.file" in request.data:
            file_obj = request.data["filecontent.file"]
        else:
            try:
                file_obj = request.stream.FILES["filecontent.file"]
            except (AttributeError, KeyError):
                pass
        if file_obj is not None:
            env_settings = get_tenant_settings().env_settings
            allowed_patterns = env_settings.community_input_allowed_mime_types
            if allowed_patterns is None:
                allowed_patterns = DEFAULT_COMMUNITY_INPUT_ALLOWED_MIME_TYPES
            declared = getattr(file_obj, "content_type", "") or ""
            error = _validate_community_input_upload(file_obj, declared, allowed_patterns)
            if error:
                return Response(
                    {"detail": error},
                    status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                )
            max_bytes = env_settings.community_input_max_upload_bytes or DEFAULT_COMMUNITY_INPUT_MAX_UPLOAD_BYTES
            if getattr(file_obj, "size", 0) > max_bytes:
                return Response(
                    {"detail": f"File exceeds the maximum upload size of {max_bytes} bytes."},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            self._mime_validated = True
        return super().create(request, *args, **kwargs)


class CommunityInputIconDownloadView(CommunityInputMixin, IconDownloadView):
    """Download a single event type icon scoped to a community input (no auth required)."""

    permission_classes = []
    authentication_classes = []
    throttle_classes = [CommunityInputScopedThrottle]
    throttle_scope = "community_input_read"

    def get(self, _request: Request, *args, **kwargs) -> FileResponse | Response:
        self.get_community_input()  # raises 404 if not found / inactive
        return IconDownloadView.get(self, _request, *args, **kwargs)
