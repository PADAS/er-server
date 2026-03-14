# ArcGIS Features Import

This document describes how features are imported from ArcGIS Online (WFS / Feature Services) into EarthRanger’s mapping models, and how **SpatialFeatureType presentation** is set and overwritten. It is intended to help diagnose issues where the import is reported to corrupt or change SpatialFeatureType presentation properties.

## Entry points

- **Scheduled**: The Celery task `automate_download_features_from_wfs` runs on a schedule; it finds all `ArcgisConfiguration` records that have a group set and enqueues `load_features_from_wfs(obj_id, group_id)` for each.
- **Manual**: From the admin, when “Download features” is used for an ArcGIS configuration, the same task `load_features_from_wfs` is enqueued with that config’s `id` and its group’s `group_id`.

Both paths run in tenant context (via `TenantQueueOnceTask`).

## High-level flow

1. **`load_features_from_wfs`** (`das/mapping/tasks.py`)
   - Resolves `ArcgisConfiguration` and the ArcGIS group via `get_wfs_config_objects(obj_id, group_id)`.
   - Deletes `ArcgisItem` rows that belong to this config but are **not** in the group’s current content (so items removed in ArcGIS are removed in DAS).
   - For each group member of type `"Feature Service"`:
     - Ensures an `ArcgisItem` exists (by ArcGIS item id), then calls **`extract_gis_data`** for that member.
   - Updates the config’s `last_download` and sends success/error messages via **`wfs_download_return_messages`**.

2. **`extract_gis_data`** (`das/mapping/esri_integration.py`)
   - For **each layer** in the Feature Service member:
     - Reads the layer’s **drawingInfo.renderer** and derives a **presentation** (see “Presentation import” below).
     - Queries the layer (with `out_sr=4326`) and gets GeoJSON (or JSON converted via `arcgis2geojson`).
     - Calls **`extract_features`** (writes to a temp file, then **`import_features_from_esri`**), passing the layer’s presentation and the `ArcgisItem`.
   - After processing all layers, deletes **SpatialFeature** rows linked to this `ArcgisItem` whose `external_id` is **not** in the set of imported global IDs (so features removed in ArcGIS are removed in DAS).
   - **SpatialFeatureType** rows are **never** deleted by this import; they are looked up or created by **name** and may be shared across sources.

3. **`import_features_from_esri`** (`das/mapping/esri_integration.py`)
   - Opens the temporary GeoJSON with GDAL and iterates over features.
   - For each feature, the **feature type name** is taken from the config’s `type_label` field (or fallback like `"FeatureType"` / `"type"`) via **`get_spatial_feature_type_name`**.
   - **SpatialFeatureType** is resolved with **`get_or_create_spatial_feature_type(feature, type_label)`**, which does **`SpatialFeatureType.objects.get_or_create(name=type_name)`** (tenant-scoped). So SFTs are identified only by **name** within the tenant.
   - If the layer used a **simple** renderer (`simple_presentation` is not None) and this is the first time we see this SFT name in this layer:
     - We **set** `spatial_feature_type.presentation = simple_presentation` and **save** the SFT, unless `arcgis_config.disable_import_feature_class_presentation` is True.
   - The feature geometry and attributes are then saved (create/update **SpatialFeature**) via **`save_esri_feature`**.

So the same **SpatialFeatureType** (by name) can be used by multiple sources (e.g. another ArcGIS config, or a file-based import). The import **does not** merge or preserve existing presentation; it **overwrites** `SpatialFeatureType.presentation` whenever it applies presentation from ArcGIS (unless presentation import is disabled).

## Presentation import

Presentation is derived from the ArcGIS layer’s **renderer** and stored in **SpatialFeatureType.presentation** (and optionally used by **SpatialFeature** via `default_presentation` when the feature has no own presentation).

### Where presentation is set

- **`import_featuretype_presentation(renderer, arcgis_config)`**
  Called once per layer with that layer’s `layer.properties.drawingInfo.renderer`.
  - If **uniqueValue** renderer: for each `uniqueValueInfos` entry, it gets-or-creates a **SpatialFeatureType** by **name** = `unique_val.value`, converts the symbol with **`get_mb_style(unique_val.symbol)`**, and sets `feature_type.presentation` to that (and saves), unless `arcgis_config.disable_import_feature_class_presentation` is True.
  - If **simple** renderer: converts the single symbol with **`get_mb_style(renderer.symbol)`** and **returns** that dict; it does **not** create or update SFTs here. The returned `simple_presentation` is passed into **`import_features_from_esri`**, where it is applied to each **SpatialFeatureType** that appears in the layer (see above).
- **`get_mb_style(symbol)`**
  Maps ArcGIS symbol types to a small Mapbox-style-like JSON (e.g. lines: `stroke`, `stroke-opacity`, `stroke-width`; polygons: `fill`, `fill-opacity`, `stroke`, etc.; picture/marker: `image`, `width`, `height`). Unsupported symbol types are logged and not converted.

### Why presentation can appear “corrupted” or “changed”

1. **Overwrite by name**
   SFTs are matched only by **name** (and tenant). If an SFT with that name already existed (e.g. from another ArcGIS layer, another config, or a file import) with different presentation, the ArcGIS import **replaces** its `presentation` with whatever comes from this layer’s renderer. There is no merge and no check that the SFT “belongs” to this ArcGIS source.

2. **Simple renderer: one style for all types in the layer**
   For a **simple** renderer, a **single** presentation dict is computed for the whole layer. Every **SpatialFeatureType** that appears in that layer (from the type field) gets that **same** presentation written to it. So if the layer contains multiple feature type names, they all end up with identical presentation after import, and any previous per-type styling is lost for those names.

3. **Unique value renderer: one style per value**
   For **uniqueValue**, each `uniqueValueInfos` entry defines a value (used as SFT name) and a symbol. We get-or-create the SFT by that name and set its presentation from that symbol. Re-running the import will overwrite again. If the same name exists from another source, that source’s presentation is overwritten.

4. **Re-import overwrites**
   Every run of the import that processes a layer will re-apply presentation from that layer’s renderer to the matching SFTs (by name), unless **Disable import feature class presentation** is checked on the **ArcgisConfiguration**. So manual edits to **SpatialFeatureType.presentation** in the admin will be lost on the next successful import for that type name.

5. **Unsupported or partial symbol conversion**
   Only a subset of ArcGIS symbol types are handled in **`get_mb_style`** (e.g. line, polygon, simple marker, picture marker). Others are skipped or fall back to defaults. That can make the stored presentation look “wrong” or incomplete compared to ArcGIS.

## Disabling presentation import

On the **ArcgisConfiguration** model, the field **`disable_import_feature_class_presentation`** (admin: “Disable import feature class presentation” or similar) controls whether the import updates **SpatialFeatureType.presentation**:

- When **True**: the import still creates/gets SFTs by name and imports features, but it **does not** set or update `SpatialFeatureType.presentation`. Existing presentation (including manually edited) is left unchanged.
- When **False** (default): presentation is derived from the layer’s renderer and written to each matching SFT as described above.

Use this flag when you want to avoid the import overwriting or “corrupting” existing SpatialFeatureType presentation (e.g. when SFTs are shared with other sources or manually curated).

## Symbology support (what pulls in correctly)

The import converts ArcGIS symbols via **`get_mb_style`** into the presentation format used by the map (stroke, fill, image, etc.). The following are supported and have been fixed for common user requests:

### Polygons: outline-only (no fill)

If you set a polygon symbol in ArcGIS Online to **outline only** (e.g. "Outline" style, or fill color with transparency 0), the import now:

- Sets **fill** to a neutral color with **fill-opacity: 0** so the map does not default to a solid fill.
- Imports **stroke** (outline color and width) from the symbol's `outline` when present.

So "outline in the color of my choice and no fill" should now pull into EarthRanger correctly.

### Points: simple symbology and "colored by name"

- **Unique value, simple marker (esriSMS)**
  When you use **Single symbol** or **Unique values** with a **Simple marker** (circle) and a **color** in ArcGIS Online, the import now converts that into a **colored circle** (SVG data URL) with the correct fill color and optional outline, instead of replacing it with a default icon. So "simple points colored by name" (unique value renderer by a name/type field, with a simple circle symbol per value) will show the correct colors in EarthRanger.

- **Picture marker (esriPMS / esriPFS)**
  Custom point symbols that use an image (picture marker) are imported as before: the image data is stored as a base64 data URL and used as the point's `image` in presentation.

### Supported symbol types

| ArcGIS symbol type | Supported | Notes |
|--------------------|-----------|--------|
| **esriSFS** (polygon) | Yes | Fill (including transparent for outline-only) and outline. |
| **esriSLS** (line) | Yes | Stroke color, opacity, width. |
| **esriSMS** (simple marker) | Yes | Colored circle (SVG), with optional outline; size preserved. |
| **esriPMS** / **esriPFS** (picture marker) | Yes | Image data URL, width, height. |
| Other (e.g. text, 3D) | No | Logged and not converted. |

## Summary

| Step | What happens |
|------|----------------|
| Task | `load_features_from_wfs` runs per (config, group); cleans up ArcgisItems and then processes each Feature Service in the group. |
| Per layer | Renderer → presentation; layer query → GeoJSON; `import_features_from_esri` creates/gets SFTs by **name** and writes presentation (unless disabled). |
| SFT matching | By **name** only (tenant-scoped). No link to ArcGIS config or item. |
| Presentation | Overwritten from ArcGIS renderer each run; no merge with existing. |
| Avoid overwriting | Set **ArcgisConfiguration.disable_import_feature_class_presentation** to True. |
