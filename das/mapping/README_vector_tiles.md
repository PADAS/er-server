# SpatialFeature Vector Tile Service

This document explains the implementation and usage of the vector tile service for the SpatialFeature model.

## Overview

The vector tile service provides efficient map rendering of spatial features through Mapbox Vector Tiles (MVT). It uses `django-vectortiles==1.0.1` and implements a generic filtering system that maintains consistency with the regular API filtering.

## Architecture

### Key Components

1. **SpatialFeatureLayer** (`mapping/vector_layers.py`)

   - Defines the vector layer configuration
   - Uses `VectorLayerFilterMixin` for generic filtering
   - Links to `SpatialFeatureFilterSet` as single source of truth

2. **SpatialFeatureTileView** (`mapping/spatialviews.py`)

   - MVT view with caching
   - Supports request-based filtering
   - Efficient cache key generation

3. **VectorLayerFilterMixin** (`mapping/vector_utils.py`)

   - Generic filtering system
   - Extracts allowed parameters from Django FilterSet
   - Ensures consistency between API and tile filtering

4. **SpatialFeatureFilterSet** (`mapping/filters.py`)
   - Single source of truth for filtering parameters
   - Used by both API views and vector tiles

## Endpoints

### Vector Tiles

```
GET /api/mapping/spatialfeatures/tiles/{z}/{x}/{y}.pbf
```

**Supported Query Parameters:**

- `feature_class`: Filter by feature type ID(s), comma-separated
- `feature_set`: Filter by display category ID(s), comma-separated
- `external_source`: Filter by external source (exact match)

**Examples:**

```bash
# Get all spatial features for tile z=10, x=327, y=791
curl "http://localhost:8000/api/mapping/spatialfeatures/tiles/10/327/791.pbf"

# Filter by specific feature classes
curl "http://localhost:8000/api/mapping/spatialfeatures/tiles/10/327/791.pbf?feature_class=1,2,3"

# Filter by feature set and external source
curl "http://localhost:8000/api/mapping/spatialfeatures/tiles/10/327/791.pbf?feature_set=conservation&external_source=gis_import"
```

## Tile Properties

Each feature in the vector tiles includes these properties:

- `id`: Feature ID
- `name`: Feature name
- `short_name`: Short name
- `description`: Feature description
- `feature_type_id`: Feature type ID
- `feature_type_name`: Feature type name (annotated)
- `feature_set_id`: Display category ID (annotated)
- `feature_set_name`: Display category name (annotated)
- `external_id`: External identifier
- `external_source`: External source

## Client-Side Usage

### Mapbox GL JS Example

```javascript
map.addSource('spatial-features', {
  type: 'vector',
  tiles: [
    'http://localhost:8000/api/mapping/spatialfeatures/tiles/{z}/{x}/{y}.pbf?feature_class=1,2'
  ],
  minzoom: 3,
  maxzoom: 24
})

map.addLayer({
  id: 'spatial-features-layer',
  type: 'fill',
  source: 'spatial-features',
  'source-layer': 'spatial_features',
  paint: {
    'fill-color': '#088',
    'fill-opacity': 0.8
  }
})
```

### Leaflet with Vector Tiles Plugin

```javascript
var vectorTileOptions = {
  vectorTileLayerStyles: {
    spatial_features: {
      fill: true,
      fillColor: '#088',
      fillOpacity: 0.8,
      stroke: true,
      color: '#066',
      weight: 2
    }
  }
}

var spatialFeatureLayer = L.vectorGrid
  .protobuf(
    'http://localhost:8000/api/mapping/spatialfeatures/tiles/{z}/{x}/{y}.pbf?feature_class=1,2',
    vectorTileOptions
  )
  .addTo(map)
```

## Caching

The vector tile service implements intelligent caching:

- **Cache Key**: Includes tile coordinates and only valid filter parameters
- **Cache Duration**: 1 hour (3600 seconds)
- **Cache Invalidation**: Automatic based on parameter changes
- **Efficiency**: Invalid parameters are excluded from cache keys

## Generic Filtering System

The implementation provides a reusable pattern for other models:

### Key Benefits

1. **Single Source of Truth**: FilterSet defines both API and tile filtering
2. **Consistency**: Same parameters work for both endpoints
3. **Maintainability**: Add/remove filters in one place
4. **Type Safety**: Django FilterSet handles validation
5. **Performance**: Only valid parameters affect caching

### Usage Pattern

To create vector tiles for another model:

1. Create a FilterSet for the model
2. Create a VectorLayer using `VectorLayerFilterMixin`
3. Create an MVTView using the caching utilities
4. Add URL configuration

Example:

```python
# filters.py
class EventFilterSet(filters.FilterSet):
    status = filters.ChoiceFilter(choices=EVENT_STATUS_CHOICES)
    priority = filters.NumberFilter()

    class Meta:
        model = Event
        fields = ['status', 'priority']

# vector_layers.py
class EventLayer(VectorLayer, VectorLayerFilterMixin):
    model = Event
    filterset_class = EventFilterSet
    # ... other configuration
```

## Management Commands

### Inspect Vector Tile Configuration

```bash
# Show basic configuration
python manage.py inspect_vector_tiles

# Show filter information
python manage.py inspect_vector_tiles --show-filters

# Show feature counts
python manage.py inspect_vector_tiles --count-features

# Test filtering functionality
python manage.py inspect_vector_tiles --test-filtering
```

## Testing

Run the vector tile tests:

```bash
# Run all mapping tests
pytest das/mapping/tests/

# Run only vector tile tests
pytest das/mapping/tests/test_vector_tiles.py

# Run with coverage
pytest das/mapping/tests/test_vector_tiles.py --cov=mapping.vector_layers --cov=mapping.vector_utils
```

## Performance Considerations

1. **Database Optimization**:

   - Uses `select_related()` for efficient joins
   - Annotated fields reduce additional queries

2. **Caching Strategy**:

   - Redis-backed caching for production
   - Parameter-aware cache keys
   - 1-hour cache duration balances freshness vs performance

3. **Zoom-Level Optimization**:
   - Consider implementing zoom-based feature simplification
   - Add feature density limits for high-zoom levels

## Troubleshooting

### Common Issues

1. **No tiles appearing**:

   - Check that `vectortiles` is in `INSTALLED_APPS`
   - Verify URL configuration is correct
   - Check that features have valid geometries

2. **Filtering not working**:

   - Ensure parameters are defined in `SpatialFeatureFilterSet`
   - Check that parameter values are valid
   - Use management command to test filtering

3. **Performance issues**:
   - Enable database query logging to identify slow queries
   - Consider adding database indexes on filtered fields
   - Monitor cache hit rates

### Debug Commands

```bash
# Check layer configuration
python manage.py inspect_vector_tiles --show-filters

# Test with sample data
python manage.py inspect_vector_tiles --test-filtering --count-features

# Check URL configuration
python manage.py show_urls | grep tiles
```

## Future Enhancements

1. **Multi-zoom Optimization**: Implement different feature sets per zoom level
2. **Spatial Indexing**: Add PostGIS spatial indexes for better performance
3. **Feature Clustering**: Implement clustering for high-density areas
4. **Dynamic Styling**: Add style parameters to tile requests
5. **Real-time Updates**: WebSocket integration for live tile updates
