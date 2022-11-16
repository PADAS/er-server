# EventType V1

## Overview
Events capture location, event time, who recorded the information, and structured data based on the event type. An Event Type is used to describe specific data to be collected using JSON Schema to specify the data capture format. A schema is defined in the "schema" field, and the UI layout is described in the "definition" field.

## Architecture
The eventtype data description is defined using [JSONSchema](https://json-schema.org/draft-04/schema#). Additionally, we developed our own definition system in JSON that defines the presentation of JSONSchema in our web UI.

### Key Design Decisions
- **Template-based rendering**: V1 uses Jinja2 templates to dynamically inject choice lists at render time
- **Dual structure**: Separates data schema from UI layout definition
- **Runtime choice resolution**: Choice lists are resolved from the database during schema rendering
- **Custom UI definition**: Uses a proprietary format for UI layout specification

## Limitations and Issues

### Schema Validation Challenges
- **Pre-render validation impossible**: Schemas cannot be validated as JSON until after template rendering
- **Template syntax errors**: Invalid Jinja2 syntax in schemas causes runtime failures
- **Choice dependency**: Schema validation requires database access to resolve choice lists
- **No static analysis**: Tools cannot analyze schemas without database context

### Template System Issues
- **Runtime rendering**: Choice lists are injected at request time, causing performance overhead
- **Complex syntax**: Template markers like `{{enum___field___names}}` are non-standard and error-prone
- **Debugging difficulty**: Template errors are hard to trace and debug
- **Version control**: Template variables make schema diffs difficult to review

### UI Definition Problems
- **Proprietary format**: Custom definition syntax is not standardized
- **Limited flexibility**: UI layout options are constrained by the custom format
- **Maintenance burden**: Custom UI system requires specialized knowledge
- **Inconsistent behavior**: UI rendering can be unpredictable across different scenarios

## Schema Section
The Schema section defines the data structure using JSON Schema with template variables for dynamic content.

### Choice and Dynamic Choice Lists

#### Choice Lists
Choice lists populate dropdowns and checkbox groups from the `Choice` database table. Each choice has:
- **value**: The actual value stored in the event data
- **display**: The human-readable text shown in the UI (enables future localization)

**Template Syntax:**
- `{{enum___field_name___values}}` - Array of choice values
- `{{enum___field_name___names}}` - Array of display names
- `{{enum___field_name___map}}` - Dictionary mapping values to display names

**Example:**
```json
{
  "carcassrep_species": {
    "type": "string",
    "title": "Species",
    "enum": {{enum___carcassrep_species___values}},
    "enumNames": {{enum___carcassrep_species___names}}
  }
}
```

#### Dynamic Choice Lists
Dynamic choices are populated from custom database queries defined in the `DynamicChoice` model. These return "value", "display" tuples where the value is typically a UUID reference to another database record.

**Template Syntax:**
- `{{query___field_name___values}}` - Array of dynamic choice values
- `{{query___field_name___names}}` - Array of dynamic choice display names

**Use Cases:**
- Subject selection from active subjects
- Location-based choices
- User-specific options
- Time-sensitive data

## Definition Section
The Definition section controls how the UI renders the form fields. It uses a custom JSON format to specify:
- Field ordering and grouping
- Bootstrap CSS classes for responsive layout
- Field-specific UI properties

### Definition Structure
```json
{
  "definition": [
    {
      "key": "field_name",
      "htmlClass": "col-lg-6"
    }
  ]
}
```

### Available Properties
- **key**: References a property from the schema section
- **htmlClass**: Bootstrap CSS classes for responsive layout
  - `col-lg-6`: Half-width on large screens
  - `col-lg-12`: Full-width on large screens
  - `col-md-4`: One-third width on medium screens
- **title**: Custom field title (overrides schema title)
- **description**: Additional field description
- **readonly**: Makes field read-only in the UI

### Layout Examples
```json
{
  "definition": [
    {
      "key": "species",
      "htmlClass": "col-lg-6",
      "title": "Animal Species"
    },
    {
      "key": "location",
      "htmlClass": "col-lg-12",
      "description": "Enter GPS coordinates or select from map"
    }
  ]
}
```

## Complete Example Schema

### Carcass Report EventType
This example shows a complete V1 eventtype for wildlife carcass reporting:

```json
{
  "schema": {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "Carcass Report (carcass_rep)",
    "type": "object",
    "properties": {
      "carcassrep_species": {
        "type": "string",
        "title": "Species",
        "enum": {{enum___carcassrep_species___values}},
        "enumNames": {{enum___carcassrep_species___names}}
      },
      "carcassrep_sex": {
        "type": "string",
        "title": "Sex of Animal",
        "enum": {{enum___carcassrep_sex___values}},
        "enumNames": {{enum___carcassrep_sex___names}}
      },
      "carcassrep_ageofanimal": {
        "type": "string",
        "title": "Age of Animal",
        "enum": {{enum___carcassrep_ageofanimal___values}},
        "enumNames": {{enum___carcassrep_ageofanimal___names}}
      },
      "carcassrep_ageofcarcass": {
        "type": "string",
        "title": "Age of Carcass",
        "enum": {{enum___carcassrep_ageofcarcass___values}},
        "enumNames": {{enum___carcassrep_ageofcarcass___names}}
      },
      "carcassrep_trophystatus": {
        "type": "string",
        "title": "Trophy Status",
        "enum": {{enum___carcassrep_trophystatus___values}},
        "enumNames": {{enum___carcassrep_trophystatus___names}}
      },
      "carcassrep_causeofdeath": {
        "type": "string",
        "title": "Cause of Death",
        "enum": {{enum___carcassrep_causeofdeath___values}},
        "enumNames": {{enum___carcassrep_causeofdeath___names}}
      }
    }
  },
  "definition": [
    {
      "key": "carcassrep_species",
      "htmlClass": "col-lg-6"
    },
    {
      "key": "carcassrep_sex",
      "htmlClass": "col-lg-6"
    },
    {
      "key": "carcassrep_ageofanimal",
      "htmlClass": "col-lg-6"
    },
    {
      "key": "carcassrep_ageofcarcass",
      "htmlClass": "col-lg-6"
    },
    {
      "key": "carcassrep_trophystatus",
      "htmlClass": "col-lg-6"
    },
    {
      "key": "carcassrep_causeofdeath",
      "htmlClass": "col-lg-6"
    }
  ]
}
```

### Rendered Schema (After Template Processing)
After the Jinja2 template is processed with actual choice data, the schema becomes valid JSON:

```json
{
  "schema": {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "Carcass Report (carcass_rep)",
    "type": "object",
    "properties": {
      "carcassrep_species": {
        "type": "string",
        "title": "Species",
        "enum": ["elephant", "lion", "rhino"],
        "enumNames": ["African Elephant", "African Lion", "White Rhino"]
      }
    }
  }
}
```

## Migration to V2

### Why Migrate?
V2 eventtypes address the major limitations of V1:
- **Static validation**: Schemas can be validated without database access
- **Standard references**: Uses JSON Schema `$ref` instead of custom templates
- **Better UI system**: Standardized UI definition format
- **Improved performance**: No runtime template rendering
- **Tool compatibility**: Works with standard JSON Schema tools

### Migration Steps
1. **Convert template variables to $ref**: Replace `{{enum___field___values}}` with `$ref` URLs
2. **Update UI definition**: Convert custom definition format to V2 UI structure
3. **Test validation**: Ensure schemas validate correctly before deployment
4. **Update version field**: Set `version = "2"` in the EventType model

### Example Migration
**V1 Template:**
```json
{
  "enum": {{enum___carcassrep_species___values}},
  "enumNames": {{enum___carcassrep_species___names}}
}
```

**V2 Reference:**
```json
{
  "anyOf": [
    {
      "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_species"
    }
  ]
}
```

For detailed migration guidance, see [EventType V2 Documentation](./eventtype_v2.md).

## Best Practices

### Schema Design
- **Use descriptive field names**: Follow consistent naming conventions (e.g., `carcassrep_species`)
- **Provide clear titles**: Use human-readable titles for all fields
- **Group related fields**: Use consistent prefixes for related fields
- **Validate template syntax**: Test Jinja2 templates before deployment

### Choice Management
- **Consistent choice values**: Use stable, URL-safe values for choices
- **Meaningful display names**: Provide clear, localized display text
- **Active choice management**: Regularly review and update choice lists
- **Document choice dependencies**: Keep track of which eventtypes use which choices

### UI Layout
- **Responsive design**: Use appropriate Bootstrap classes for different screen sizes
- **Logical field ordering**: Arrange fields in a logical workflow order
- **Consistent spacing**: Use consistent column widths for visual harmony
- **Accessibility**: Ensure form fields are properly labeled and accessible

## Troubleshooting

### Common Issues

#### Template Rendering Errors
**Problem**: Schema fails to render with Jinja2 errors
**Solution**:
- Check template syntax for typos in `{{enum___field___values}}` format
- Verify choice field names exist in the database
- Test template rendering in development environment

#### Invalid JSON Schema
**Problem**: Rendered schema is not valid JSON
**Solution**:
- Ensure all template variables are properly closed
- Check for missing commas or brackets
- Validate rendered schema with JSON Schema validator

#### Choice List Not Populating
**Problem**: Dropdown shows empty or incorrect options
**Solution**:
- Verify choice records exist in the database
- Check choice field names match template references
- Ensure choices are marked as active (`is_active=True`)

#### UI Layout Issues
**Problem**: Form fields not displaying correctly
**Solution**:
- Verify definition keys match schema property names
- Check Bootstrap CSS classes are valid
- Ensure definition array is properly formatted

### Debugging Tips
1. **Test template rendering**: Use Django shell to test template rendering
2. **Validate JSON**: Use online JSON validators for rendered schemas
3. **Check database**: Verify choice data exists and is active
4. **Review logs**: Check application logs for template rendering errors

## Legacy Support

V1 eventtypes are maintained for backward compatibility but are not recommended for new implementations. Existing V1 eventtypes should be migrated to V2 when possible to take advantage of improved validation, performance, and tooling support.
