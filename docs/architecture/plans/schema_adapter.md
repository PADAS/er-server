# Schema Adapter

The `SchemaAdapter` provides a unified interface for accessing both V1 (legacy) and V2 (new) event type schemas. This solves the problem where code like `EventsExportView` couldn't properly access schema properties and values from V2 schemas.

See [ERA-11870](https://allenai.atlassian.net/browse/ERA-11870)

## Problem Solved

Previously, the `EventsExportView` was using V1-specific functions like:
- `schema_utils.get_display_values_for_event_details()`
- `schema_utils.get_column_header_name()`
- `schema_utils.property_keys_order_as_dict()`

These functions expected V1 schema structure (`schema["schema"]["properties"]`) but V2 schemas have a different structure (`schema["json"]["properties"]`).

## Solution

The `SchemaAdapter` abstracts the differences between V1 and V2 schemas:

### V1 Schema Structure
```json
{
  "schema": {
    "properties": { ... }
  },
  "definition": [ ... ]
}
```

### V2 Schema Structure
```json
{
  "json": {
    "properties": { ... }
  },
  "ui": {
    "fields": { ... },
    "order": [ ... ]
  }
}
```

## Usage

### Basic Usage
```python
from activity.schemas.schema_adapter import SchemaAdapterFactory

# Create adapter from schema string or dict
adapter = SchemaAdapterFactory.create_adapter(schema_string, request)

# Get properties
properties = adapter.get_properties()

# Get property order
order = adapter.get_property_order()

# Get column header name
header = adapter.get_column_header_name("field_name")

# Get display values for event details
display_values = adapter.get_display_values_for_event_details(event_details)
```

### From EventType
```python
from activity.schemas.schema_adapter import SchemaAdapterFactory

# Create adapter from EventType instance
adapter = SchemaAdapterFactory.create_from_event_type(event_type, request)
```

## Implementation Details

### SchemaAdapter Protocol
- Uses Python's `typing.Protocol` for structural subtyping
- Defines the interface that all schema adapters must implement
- More flexible than ABC (Abstract Base Classes) - no inheritance required
- Enables duck typing while maintaining type safety

### V1SchemaAdapter
- Uses the existing `schema_utils` functions
- Renders the schema using Django templates
- Extracts properties from `schema["schema"]["properties"]`
- Gets order from `schema["definition"]`

### V2SchemaAdapter
- Uses the `EventTypeSchemaService` for rendering
- Handles JSON Schema references and dereferencing
- Extracts properties from `schema["json"]["properties"]`
- Gets order from `schema["ui"]["order"]`
- Falls back to V1 logic for display values after rendering
- After rendering, choice fields resolved from dynamic schema URLs use **`enum`** plus **`x-enumExtra`** (per-value `title` / `description` / extras); the adapter reads those in addition to legacy `anyOf` / `oneOf` shapes where they still appear

### SchemaAdapterFactory
- Automatically detects V1 vs V2 schema structure
- Creates the appropriate adapter
- Handles JSON parsing errors gracefully

## Updated EventsExportView

The `EventsExportView` now uses the schema adapter instead of direct `schema_utils` calls:

```python
# Old code
current_schema = renderer(event_type["schema"])
current_schema_order = schema_utils.property_keys_order_as_dict(current_schema)
details = schema_utils.get_display_values_for_event_details(event_details, current_schema)

# New code
schema_adapter = SchemaAdapterFactory.create_adapter(event_type["schema"], self.request)
current_schema_order = schema_adapter.get_property_order()
details = schema_adapter.get_display_values_for_event_details(event_details)
```

This allows the export view to work with both V1 and V2 schemas transparently.
