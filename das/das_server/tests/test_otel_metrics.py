from __future__ import annotations

from unittest.mock import MagicMock, patch

from das_server.otel_metrics import GCPOTLPMetricExporter


class TestGCPOTLPMetricExporter:
    def _make_exporter(
        self, credentials: object, project: str | None, **extra_kwargs: object
    ) -> tuple[GCPOTLPMetricExporter, MagicMock, MagicMock, MagicMock]:
        with (
            patch("das_server.otel_metrics.google.auth.transport.requests.AuthorizedSession") as mock_session_cls,
            patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter.__init__") as mock_init,
        ):
            mock_init.return_value = None
            session = MagicMock()
            session.headers = {}
            mock_session_cls.return_value = session
            exporter = GCPOTLPMetricExporter(credentials=credentials, project=project, **extra_kwargs)
            return exporter, mock_session_cls, mock_init, session

    def test_builds_authorized_session_from_credentials(self):
        creds = MagicMock()
        _, mock_session_cls, _, _ = self._make_exporter(creds, "my-project")
        mock_session_cls.assert_called_once_with(creds)

    def test_passes_session_to_parent_init(self):
        creds = MagicMock()
        _, _, mock_init, session = self._make_exporter(creds, "my-project")
        _, kwargs = mock_init.call_args
        assert kwargs["session"] is session
        assert kwargs["endpoint"] == "https://telemetry.googleapis.com/v1/metrics"

    def test_sets_user_project_header_when_project_known(self):
        creds = MagicMock()
        _, _, _, session = self._make_exporter(creds, "my-project")
        assert session.headers["x-goog-user-project"] == "my-project"

    def test_does_not_set_user_project_header_when_project_none(self):
        creds = MagicMock()
        with patch("das_server.otel_metrics.settings") as mock_settings:
            mock_settings.GCP_PROJECT_ID = ""
            _, _, _, session = self._make_exporter(creds, None)
        assert "x-goog-user-project" not in session.headers

    def test_falls_back_to_settings_project(self):
        creds = MagicMock()
        with patch("das_server.otel_metrics.settings") as mock_settings:
            mock_settings.GCP_PROJECT_ID = "settings-project"
            _, _, _, session = self._make_exporter(creds, None)
        assert session.headers["x-goog-user-project"] == "settings-project"

    def test_passes_max_export_batch_size_of_200_to_parent_init(self):
        creds = MagicMock()
        _, _, mock_init, _ = self._make_exporter(creds, "my-project")
        _, kwargs = mock_init.call_args
        assert kwargs["max_export_batch_size"] == 200

    def test_does_not_override_explicit_max_export_batch_size(self):
        creds = MagicMock()
        _, _, mock_init, _ = self._make_exporter(creds, "my-project", max_export_batch_size=50)
        _, kwargs = mock_init.call_args
        assert kwargs["max_export_batch_size"] == 50

    def test_export_diagnostic_reads_from_auth_session(self):
        creds = MagicMock()
        exporter, _, _, session = self._make_exporter(creds, "my-project")
        session.headers["authorization"] = "Bearer tok"

        response = MagicMock()
        response.status_code = 403
        response.text = "permission denied"

        with (
            patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter._export") as mock_super,
            patch("das_server.otel_metrics.logger") as mock_logger,
        ):
            mock_super.return_value = response
            result = exporter._export()

        assert result is response
        assert mock_logger.warning.called
        message = mock_logger.warning.call_args[0][0]
        assert "auth_present" not in message

    def test_no_export_override_present(self):
        # The old header-mutating export() override has been removed in favor
        # of AuthorizedSession; the class must inherit the parent's export().
        assert "export" not in GCPOTLPMetricExporter.__dict__
        assert "_ensure_credentials" not in GCPOTLPMetricExporter.__dict__
