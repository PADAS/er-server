from django.urls import path

from usercontent.chunked_upload import (
    ChunkedUploadChunkView,
    ChunkedUploadCompleteView,
    ChunkedUploadInitView,
    ChunkedUploadStatusView,
)
from usercontent.views import UserContentDownloadView

urlpatterns = [
    path("<uuid:usercontent_id>/", UserContentDownloadView.as_view(), name="usercontent-download"),
    path("chunked-uploads/", ChunkedUploadInitView.as_view(), name="chunked-upload-init"),
    path(
        "chunked-uploads/<uuid:upload_id>/",
        ChunkedUploadStatusView.as_view(),
        name="chunked-upload-status",
    ),
    path(
        "chunked-uploads/<uuid:upload_id>/chunks/<int:chunk_index>/",
        ChunkedUploadChunkView.as_view(),
        name="chunked-upload-chunk",
    ),
    path(
        "chunked-uploads/<uuid:upload_id>/complete/",
        ChunkedUploadCompleteView.as_view(),
        name="chunked-upload-complete",
    ),
]
