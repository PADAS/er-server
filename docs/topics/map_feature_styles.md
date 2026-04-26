ER map feature styles
=====================

EarthRanger styles spatial features using the [SimpleStyle](https://github.com/mapbox/simplestyle-spec) convention — a small JSON dictionary stored alongside each feature or feature type. The same dictionary surfaces in both the GeoJSON endpoints and the vector tile output, so a single style definition drives all clients.

## Where the style lives

- `SpatialFeatureType.presentation` — JSONB column, the default styling for every feature of that type.
- `SpatialFeature.presentation` — JSONB column, optional per-feature override. Populated by importers (e.g. ArcGIS, GeoJSON upload) and the API; not editable through the admin.
- Resolution order: `feature.presentation` (if non-empty) → `feature_type.presentation` → `{}`. Exposed by the `SpatialFeature.default_presentation` property.

## Supported keys

All keys follow the SimpleStyle convention — they're feature properties, not Mapbox-style paint properties.

| Key                   | Geometry        | Type      | Notes                                            |
|-----------------------|-----------------|-----------|--------------------------------------------------|
| `stroke`              | line, polygon   | hex color | Outline color.                                   |
| `stroke-width`        | line, polygon   | number    | Pixels.                                          |
| `stroke-opacity`      | line, polygon   | 0.0–1.0   |                                                  |
| `fill`                | polygon         | hex color | Polygon fill color. **Canonical key** (see below). |
| `fill-opacity`        | polygon         | 0.0–1.0   |                                                  |
| `fill-outline-color`  | polygon         | hex color | Outline of the fill (Mapbox paint name; tolerated as a feature property for editor parity). |
| `image`               | point           | URL/path  | Icon. Accepts absolute URL, `/static/...`, or `data:` URI. |
| `width`               | point           | number    | Icon width in pixels.                            |
| `height`              | point           | number    | Icon height in pixels.                           |

Hex colors accept 3- or 6-digit form (`#fff`, `#ffffff`).

## `fill` vs `fill-color`

`fill` is the SimpleStyle feature-property name. `fill-color` is the Mapbox style-spec **paint** property — it belongs on a style layer, not on a feature. Some legacy data (older hand-edits, non-standard imports) put `fill-color` on the feature. The codebase tolerates that:

- **Read path:** vector tiles expose both `fill` and `fill-color` as separate flat tile properties when present. GeoJSON endpoints flatten whichever key the JSON contains. Mapbox/MapLibre style layers should reference `["get", "fill"]`.
- **Editor read:** if a feature_type's presentation has `fill-color` but no `fill`, the polygon-fill picker loads the legacy value so the user sees the actual stored color.
- **Editor write:** the editor only writes `fill`. When saving, `fill-color` is dropped if `fill` is set. Opening any legacy feature_type in the editor and saving normalizes its presentation forward.

Once stored data is fully migrated, the `fill-color` tolerance in `vector_layers.SpatialFeatureLayer.presentation_keys` can be removed.

## How styles surface to clients

### GeoJSON endpoints

`FeatureGeoJsonView` and `FeatureSetGeoJsonView` flatten the resolved presentation onto the feature's `properties`. Clients see SimpleStyle keys at the top level — there is no nested `presentation` object:

```json
{
  "type": "Feature",
  "properties": {
    "title": "...",
    "stroke": "#ffffff",
    "stroke-width": 3,
    "fill": "#555555",
    "fill-opacity": 0
  },
  "geometry": { ... }
}
```

The flattening is performed by the custom GeoJSON serializer in `das/core/serializers.py`.

### Vector tiles (`SpatialFeatureLayer`)

Each supported key is emitted as its own flat tile property. Style layers reference them through expressions, e.g. for a fill layer:

```json
{
  "type": "fill",
  "paint": {
    "fill-color": ["get", "fill"],
    "fill-opacity": ["get", "fill-opacity"]
  }
}
```

Note the asymmetry: the **paint** property is `fill-color` (Mapbox style-spec); the **feature** property it reads is `fill` (SimpleStyle).

## Editing presentation

The SpatialFeatureType admin (`/admin/mapping/spatialfeaturetype/`) provides a per-geometry-type editor with color pickers, sliders, and live previews. The editor reads from and writes to the same `presentation` JSON column — there are no separate columns. An "Advanced" textarea exposes the raw JSON for power users; arbitrary keys placed there are preserved on save.

Per-feature overrides (`SpatialFeature.presentation`) are not editable in the admin and are typically populated by importers.

## ArcGIS imports

ArcGIS imports derive a SimpleStyle-shaped dict from the source layer's renderer and write it to `SpatialFeatureType.presentation`. See `docs/topics/arcgis-features.md` for the renderer mapping, the overwrite semantics, and the `disable_import_feature_class_presentation` flag for opting out.

---

# Style cookbook

Reference values for common feature types.

## Boundaries
- National Park: {"fill": "#555555", "fill-opacity": 0, "stroke": "#00FFFF", "stroke-opacity": 0.7, "stroke-width": 3}
- National Reserve: {"fill": "#7CB74B", "fill-opacity": 0.2, "stroke": "#4E633C", "stroke-opacity": 0.5, "stroke-width": 2}
- Wildlife Reserve:
- Community Conservancy: {"fill": "#555555", "fill-opacity": 0, "stroke": "#FFC0CB", "stroke-opacity": 0.7,  "stroke-width": 3}
- Conservancy: {"fill": "#00FF00", "fill-opacity": 0.1, "stroke": "#87CEFA", "stroke-opacity": 0.7,  "stroke-width": 3}
- Conservation Area: {"fill": "#FAD5C4", "fill-opacity": 0.2, "stroke": "#FF5733", "stroke-opacity": 0.5, "stroke-width": 2}
- Corridor: {"fill": "#555555", "fill-opacity": 0.2, "stroke": "#86b86e", "stroke-opacity": 0.7, "stroke-width": 2}
- Patrol Block / Sector: {"fill": "#555555", "fill-opacity": 0, "stroke": "#87CEFA", "stroke-opacity": 0.7, "stroke-width": 1}
- Forest Reserve: {"fill": "#e4ffe2", "fill-opacity": 0.2, "stroke": "#aee88d", "stroke-opacity": 0.5, "stroke-width": 2}
- Forest Concession:
- Forest Conservation Area [ndoki]: {
- Wildlife Sanctuary: {"fill": "#ffffc9", "fill-opacity": 0.2, "stroke": "#efef4f", "stroke-opacity": 0.5, "stroke-width": 2}

## Roads
- Primary: {"stroke": "#ffffff", "stroke-opacity": 0.5, "stroke-width": 3}
- Secondary: {"stroke": "#ffffff", "stroke-opacity": 0.5, "stroke-width": 2}
- Tertiary: {"stroke": "#ffffff", "stroke-opacity": 0.5, "stroke-width": 1}
- Railway: {"stroke": "#ffffff", "stroke-opacity": 0.5, "stroke-width": 1}

## Rivers
- Primary: {"stroke": "#05e6ff", "stroke-opacity": 0.5, "stroke-width": 3}
- Secondary: {"stroke": "#05e6ff", "stroke-opacity": 0.5, "stroke-width": 2}
- Tertiary: {"stroke": "#05e6ff", "stroke-opacity": 0.5, "stroke-width": 1}

## POI
- Points of Interest [*generic*]: {"image": "/static/feature-POI-star_flag.svg"}
- Bai_Forest Clearing: {"image": "/static/bai-green.svg"}
- Fence Attendant House: {"image": "/static/fence_attendant_house.svg"}
- Tourism Center: {"image": "/static/tourism_center-black.svg"}
- Campsite: {"image": "/static/campsite-olive.svg"}
- Hotel/Lodge: {"image": "/static/lodging-black.svg"}
- Gate Post: {"image": "/static/park_gate.svg"}
- Picnic/Rest Stop: {"image": "/static/picnic_spot-black.svg"}
- Boma [*lion*]: {"image": "/static/lion_sighting-med_green.svg"}
- Viewpoint: {"image": "/static/viewpoint-black.svg"}
- Jetty: {"image": "/static/jetty-black.svg"}
- Airstrip (point): {"image": "/static/plane-gray.svg}

## Operational
- Headquarters: {"image": "/static/park_HQ-olive.svg"}
- Ranger Station: {"image": "static/ranger_post-dk_olive.svg"}
- Ranger Post: {"image": "static/ranger_post-dk_olive.svg"}
- Ranger Camp: {"image": "/static/campsite-olive.svg"}

## Fences
- Fencing_Unknown (generic): {"stroke": "#ffaf01", "stroke-opacity": 0.8, "stroke-width": 2}
