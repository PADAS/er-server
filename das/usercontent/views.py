from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import FileResponse, Http404
from django.utils.http import content_disposition_header

from usercontent.models import ImageFileContent
from usercontent.serializers import get_image_rendition_keys, get_stored_filename
from usercontent.storage_paths import force_download_content_headers
from usercontent.utils import guess_content_type, resolve_usercontent_for_tenant

logger = logging.getLogger(__name__)


class UserContentDownloadView(APIView):
    """Stream a previously-uploaded file to any authenticated user in the same tenant.

    Access control rests on two factors, not on a per-user ownership check:

    * **UUID unguessability** — the content ID is a random UUIDv4 (122 bits of
      entropy), so it cannot be enumerated or guessed.
    * **Tenant scope** — lookup goes through ``resolve_usercontent_for_tenant``, which
      uses the tenant-scoped ORM manager, so a UUID from another tenant returns 404.

    Any authenticated user in the tenant who holds the UUID may download the file.
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Download uploaded usercontent file",
        description=(
            "Stream the raw bytes of a file that was previously uploaded via the chunked-upload "
            "pipeline.  Any authenticated user within the same tenant can download the file "
            "(tenant isolation is enforced automatically; cross-tenant IDs return 404).  "
            "Returns 404 for unknown IDs and cross-tenant IDs, 401 for anonymous requests.  "
            "Access control relies on UUID unguessability (a random 122-bit UUIDv4) combined "
            "with tenant scope; there is no per-user ownership check — any authenticated user "
            "in the tenant who holds the ID may download the file."
        ),
        parameters=[
            OpenApiParameter(
                name="rendition",
                location=OpenApiParameter.QUERY,
                description=(
                    "Optional image rendition to serve.  Valid names are the configured rendition "
                    "keys (e.g. icon, thumbnail, large, xlarge); omit or pass 'original' to get "
                    "the full-size file.  Applies to images only — a rendition request on a "
                    "non-image file, or an unknown rendition name, returns 404."
                ),
                required=False,
                type=str,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description=(
                    "File bytes with the original filename.  Active MIME types "
                    "(SVG, HTML, JS) are forced to download as "
                    "`application/octet-stream` attachments to prevent inline "
                    "rendering under the app origin; all other types stream inline.  "
                    "`X-Content-Type-Options: nosniff` is always set."
                ),
            ),
            401: OpenApiResponse(description="Authentication credentials were not provided."),
            404: OpenApiResponse(
                description="No file found for this ID in the current tenant, or unknown rendition name."
            ),
        },
    )
    def get(self, request: Request, usercontent_id: object) -> Response:
        instance = resolve_usercontent_for_tenant(usercontent_id)
        if instance is None:
            raise Http404

        rendition = request.query_params.get("rendition")
        if rendition:
            if rendition not in get_image_rendition_keys() or not isinstance(instance, ImageFileContent):
                raise Http404
            try:
                rendition_name = get_stored_filename(instance.file, rendition_set="default", rendition_key=rendition)
                fp = instance.file.field.storage.open(rendition_name, "rb")
            except Exception:
                logger.exception("Failed to open usercontent rendition %s (%s) from storage", usercontent_id, rendition)
                raise Http404
        else:
            try:
                fp = instance.file.open("rb")
            except Exception:
                logger.exception("Failed to open usercontent file %s from storage", usercontent_id)
                raise Http404

        forced_ct, _ = force_download_content_headers(instance.filename)
        if forced_ct:
            content_type = forced_ct  # "application/octet-stream"
            as_attachment = True
        else:
            content_type = guess_content_type(instance.filename)
            as_attachment = False
        response = FileResponse(fp, content_type=content_type)
        response["Content-Disposition"] = content_disposition_header(
            as_attachment=as_attachment, filename=instance.filename
        )
        response["X-Content-Type-Options"] = "nosniff"  # unconditional
        return response
