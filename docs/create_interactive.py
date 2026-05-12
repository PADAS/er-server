"""Generate docs/_extra/interactive/index.html for the Swagger UI page."""

from __future__ import annotations

import importlib.resources
import pathlib
import shutil

out = pathlib.Path(__file__).parent / "_extra" / "interactive"
out.mkdir(parents=True, exist_ok=True)

# Copy swagger-ui assets from drf_spectacular_sidecar so the page works without network access.
sidecar = (
    importlib.resources.files("drf_spectacular_sidecar") / "static" / "drf_spectacular_sidecar" / "swagger-ui-dist"
)
for asset in ("swagger-ui.css", "swagger-ui-bundle.js"):
    with importlib.resources.as_file(sidecar / asset) as src:
        shutil.copy2(src, out / asset)

(out / "index.html").write_text(
    """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>EarthRanger Interactive API</title>
  <link rel="stylesheet" href="swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "../_static/openapi/schema.yaml",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
    });
  </script>
</body>
</html>
"""
)
