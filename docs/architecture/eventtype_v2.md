# EventType V2

## Overview
EventType V2 represents a complete redesign of the eventtype system, addressing fundamental limitations in V1 while providing a modern, standards-based approach to defining event data collection schemas. V2 uses JSON Schema 2020-12 with reference resolution and a comprehensive UI definition system.

## Key Improvements Over V1

### Schema Validation & Standards
- **Static validation**: Schemas can be validated without database access or template rendering
- **JSON Schema 2020-12**: Uses the latest JSON Schema standard with full tooling support
- **Reference resolution**: Standard `$ref` system replaces custom template variables
- **Type safety**: Strong typing with comprehensive field type support

### Performance & Reliability
- **No runtime rendering**: Eliminates Jinja2 template processing overhead
- **Predictable behavior**: Consistent schema resolution without template dependencies
- **Better caching**: Static schemas enable effective caching strategies
- **Error handling**: Comprehensive validation and error reporting

### Developer Experience
- **Tool compatibility**: Works with standard JSON Schema validators and editors
- **Better debugging**: Clear error messages and validation feedback
- **Version control**: Clean diffs without template variables
- **Documentation**: Self-documenting schemas with proper metadata

### UI System
- **Standardized format**: Consistent UI definition structure
- **Rich field types**: Support for text, numeric, choice, attachment, and collection fields
- **Responsive design**: Built-in support for responsive layouts
- **Accessibility**: Better accessibility support through standardized definitions

## Architecture

V2 eventtypes use a dual-structure approach with separate JSON schema and UI definition sections, similar to V1 but with significant improvements in implementation and standards compliance.

### Core Design Principles

#### 1. Standards-Based Schema Definition
- **JSON Schema 2020-12**: Uses the latest JSON Schema standard for maximum compatibility
- **Reference Resolution**: Implements [JSON Schema References](https://json-schema.org/understanding-json-schema/structuring.html#ref) for dynamic content
- **Static Validation**: Schemas can be validated without database access or runtime processing

#### 2. Reference-Based Choice Resolution
V2 replaces V1's template variables with standard JSON Schema `$ref` references:

**V1 Template Approach:**
```json
{
  "enum": {{enum___carcassrep_species___values}},
  "enumNames": {{enum___carcassrep_species___names}}
}
```

**V2 Reference Approach:**
```json
{
  "anyOf": [
    {
      "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_species"
    }
  ]
}
```

When the reference is resolved (for example in a pre-rendered event type schema), dynamic schema endpoints expand to an **`enum`** list of allowed values plus **`x-enumExtra`**: an object keyed by each enum value whose values hold a **`display`** string, optional **`description`**, and any extra keys mapped from **`x_<name>`** query parameters (for example **`x_icon=icon_url`**). Callers select source paths with **`s_value`**, **`s_label`**, **`s_description`**, **`s_format`**, and **`s_type`**. Schema mapping uses the **`s_`** / **`x_`** prefix so those keys do not overlap typical list API query parameters on the embedded endpoints. Use **`s_format=oneOf`** if you need the **`const`** / **`title`** branch layout. This keeps validators from compiling thousands of **`oneOf`** / **`anyOf`** branches while preserving display metadata.

##### Pipeline & internal rendering

`DynamicSchemaFromSourceView` follows a small pipeline: it pulls the source rows from the embedded list view (`get_data_from_source_view`), maps each row to output keys via `get_schema_items` (driven by `get_fields_map`, with optional `get_<field>_from_item` hooks), then hands the mapped rows to the fragment serializer chosen by **`s_format`** (`serialize_enum_fragment` / `serialize_one_of_fragment`, registered in `schemas.format_serializers`).

Internal consumers that cannot deal with two shapes (currently `AlertingSchemaPropertiesAdapter`, which speaks `anyOf` / `oneOf`) wrap their call in `output_format_override(OUTPUT_FORMAT_ONE_OF)`. The override is a `ContextVar` checked by `DynamicSchemaFromSourceView.get_output_format` *before* `s_format` / `default_format`, so any nested `$ref` expansion produced during dereferencing comes back as **`oneOf`** regardless of the source view's default. Public API endpoints are unaffected — they only see the override if their request is itself made inside one.

#### 3. Enhanced Field Type System
V2 supports comprehensive field types with proper JSON Schema definitions:

- **Text Fields**: Short text, long text, email, URL
- **Numeric Fields**: Integer, number, with min/max constraints
- **Choice Fields**: Single and multi-select with reference resolution
- **Date/Time Fields**: Date, time, datetime with timezone support
- **Location Fields**: Point and polygon geometries
- **Attachment Fields**: File uploads with type restrictions
- **Collection Fields**: Nested object collections

#### 4. Modern UI Definition System
The UI system provides:
- **Field-specific configurations**: Each field type has tailored UI options
- **Responsive layouts**: Built-in support for different screen sizes
- **Section organization**: Logical grouping of related fields
- **Accessibility support**: Proper labeling and ARIA attributes

## JSON Schema Structure

V2 eventtypes use a two-section structure: `json` for data schema and `ui` for interface definition.

### Schema Structure
```json
{
  "json": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "properties": {
      "field_name": {
        "type": "string",
        "title": "Field Title",
        "description": "Field description",
        "deprecated": false
      }
    },
    "required": ["field_name"],
    "type": "object"
  },
  "ui": {
    "fields": { /* UI field configurations */ },
    "sections": { /* Layout sections */ },
    "order": ["section-1"],
    "headers": {}
  }
}
```

### Field Types

#### Text Fields
```json
{
  "field_name": {
    "type": "string",
    "title": "Text Field",
    "description": "A text input field",
    "minLength": 1,
    "maxLength": 255,
    "pattern": "^[A-Za-z0-9\\s]*$"
  }
}
```

#### Numeric Fields
```json
{
  "field_name": {
    "type": "number",
    "title": "Numeric Field",
    "description": "A numeric input field",
    "minimum": 0,
    "maximum": 100,
    "multipleOf": 0.1
  }
}
```

#### Choice Fields (Single Select)
```json
{
  "field_name": {
    "type": "string",
    "title": "Choice Field",
    "description": "Select one option",
    "anyOf": [
      {
        "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=field_name"
      }
    ]
  }
}
```

#### Choice List Fields (Multi-Select)
```json
{
  "field_name": {
    "type": "array",
    "title": "Choice List Field",
    "description": "Select multiple options",
    "items": {
      "anyOf": [
        {
          "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=field_name"
        }
      ]
    },
    "uniqueItems": true,
    "minItems": 1,
    "maxItems": 5
  }
}
```

#### Date/Time Fields
```json
{
  "field_name": {
    "type": "string",
    "title": "Date Field",
    "description": "Select a date",
    "format": "date"
  }
}
```

#### Location Fields
```json
{
  "field_name": {
    "type": "object",
    "title": "Location Field",
    "description": "Select a location",
    "properties": {
      "type": {"const": "Point"},
      "coordinates": {
        "type": "array",
        "items": {"type": "number"},
        "minItems": 2,
        "maxItems": 2
      }
    },
    "required": ["type", "coordinates"]
  }
}
```

#### Attachment Fields
```json
{
  "field_name": {
    "type": "array",
    "title": "Attachment Field",
    "description": "Upload files",
    "items": {
      "type": "object",
      "properties": {
        "filename": {"type": "string"},
        "content_type": {"type": "string"},
        "size": {"type": "integer"}
      }
    }
  }
}
```

## UI Definition System

The UI system defines how fields are presented and organized in the user interface.

### UI Structure
```json
{
  "ui": {
    "fields": {
      "field_name": {
        "type": "TEXT",
        "inputType": "SHORT_TEXT",
        "placeholder": "Enter text here",
        "parent": "section-1"
      }
    },
    "sections": {
      "section-1": {
        "label": "Main Section",
        "columns": 2,
        "isActive": true,
        "leftColumn": [
          {"name": "field_name", "type": "field"}
        ],
        "rightColumn": []
      }
    },
    "order": ["section-1"],
    "headers": {}
  }
}
```

### Field UI Types

#### Text Fields
```json
{
  "type": "TEXT",
  "inputType": "SHORT_TEXT", // or "LONG_TEXT"
  "placeholder": "Enter text here",
  "parent": "section-1"
}
```

#### Numeric Fields
```json
{
  "type": "NUMBER",
  "inputType": "NUMBER",
  "placeholder": "Enter number",
  "parent": "section-1"
}
```

#### Choice Fields
```json
{
  "type": "CHOICE_LIST",
  "inputType": "DROPDOWN", // or "RADIO", "CHECKBOX"
  "choices": {
    "type": "EXISTING_CHOICE_LIST",
    "existingChoiceList": ["choice_field_name"],
    "eventTypeCategories": [],
    "featureCategories": [],
    "subjectGroups": [],
    "subjectSubtypes": [],
    "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP"
  },
  "placeholder": "Select option",
  "parent": "section-1"
}
```

#### Attachment Fields
```json
{
  "type": "ATTACHMENT",
  "allowableFileTypes": ["image", "document", "video", "audio"],
  "parent": "section-1"
}
```

#### Collection Fields
```json
{
  "type": "COLLECTION",
  "parent": "section-1"
}
```

### Section Configuration
```json
{
  "sections": {
    "section-1": {
      "label": "Basic Information",
      "columns": 2,
      "isActive": true,
      "leftColumn": [
        {"name": "field1", "type": "field"},
        {"name": "field2", "type": "field"}
      ],
      "rightColumn": [
        {"name": "field3", "type": "field"}
      ]
    }
  }
}
```

## Reference Resolution System

V2 uses JSON Schema references to resolve dynamic content like choice lists.

### Choice Reference URLs
Choice lists are resolved through API endpoints:
```
https://api.example.com/v2.0/schemas/choices.json?field=field_name
```

### Reference Resolution Process
1. **Schema Validation**: Initial validation of schema structure
2. **Reference Discovery**: Identification of `$ref` URLs in the schema
3. **Reference Resolution**: Fetching and resolving referenced content
4. **Schema Completion**: Final validation of the complete schema

### Resolved Choice Format
After resolution, choice references become:
```json
{
  "anyOf": [
    {
      "const": "value1",
      "title": "Display Name 1"
    },
    {
      "const": "value2",
      "title": "Display Name 2"
    }
  ]
}
```

## Complete Example

### Wildlife Carcass Report EventType
This example demonstrates a complete V2 eventtype for wildlife carcass reporting:

```json
{
  "json": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": false,
    "properties": {
      "carcassrep_species": {
        "deprecated": false,
        "description": "Species of the animal carcass",
        "title": "Species",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_species"
          }
        ]
      },
      "carcassrep_sex": {
        "deprecated": false,
        "description": "Sex of the animal",
        "title": "Sex of Animal",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_sex"
          }
        ]
      },
      "carcassrep_ageofanimal": {
        "deprecated": false,
        "description": "Estimated age of the animal at death",
        "title": "Age of Animal",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_ageofanimal"
          }
        ]
      },
      "carcassrep_ageofcarcass": {
        "deprecated": false,
        "description": "Estimated age of the carcass when found",
        "title": "Age of Carcass",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_ageofcarcass"
          }
        ]
      },
      "carcassrep_trophystatus": {
        "deprecated": false,
        "description": "Trophy status of the animal",
        "title": "Trophy Status",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_trophystatus"
          }
        ]
      },
      "carcassrep_causeofdeath": {
        "deprecated": false,
        "description": "Suspected cause of death",
        "title": "Cause of Death",
        "type": "string",
        "anyOf": [
          {
            "$ref": "https://api.example.com/v2.0/schemas/choices.json?field=carcassrep_causeofdeath"
          }
        ]
      },
      "carcassrep_notes": {
        "deprecated": false,
        "description": "Additional observations and notes",
        "title": "Notes",
        "type": "string",
        "maxLength": 1000
      }
    },
    "required": ["carcassrep_species", "carcassrep_sex"],
    "type": "object"
  },
  "ui": {
    "fields": {
      "carcassrep_species": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_species"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select species",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_sex": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_sex"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select sex",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_ageofanimal": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_ageofanimal"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select age",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_ageofcarcass": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_ageofcarcass"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select carcass age",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_trophystatus": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_trophystatus"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select trophy status",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_causeofdeath": {
        "choices": {
          "eventTypeCategories": [],
          "existingChoiceList": ["carcassrep_causeofdeath"],
          "featureCategories": [],
          "myDataType": "SUBJECTS_FROM_SUBJECT_GROUP",
          "subjectGroups": [],
          "subjectSubtypes": [],
          "type": "EXISTING_CHOICE_LIST"
        },
        "inputType": "DROPDOWN",
        "placeholder": "Select cause of death",
        "type": "CHOICE_LIST",
        "parent": "section-1"
      },
      "carcassrep_notes": {
        "inputType": "LONG_TEXT",
        "placeholder": "Enter additional observations...",
        "type": "TEXT",
        "parent": "section-1"
      }
    },
    "headers": {},
    "order": ["section-1"],
    "sections": {
      "section-1": {
        "columns": 2,
        "isActive": true,
        "label": "Carcass Information",
        "leftColumn": [
          {"name": "carcassrep_species", "type": "field"},
          {"name": "carcassrep_sex", "type": "field"},
          {"name": "carcassrep_ageofanimal", "type": "field"}
        ],
        "rightColumn": [
          {"name": "carcassrep_ageofcarcass", "type": "field"},
          {"name": "carcassrep_trophystatus", "type": "field"},
          {"name": "carcassrep_causeofdeath", "type": "field"}
        ]
      }
    }
  }
}
```

## Validation and Error Handling

V2 eventtypes provide comprehensive validation at multiple levels:

### Schema Validation
- **JSON Schema compliance**: Validates against JSON Schema 2020-12 standard
- **Reference resolution**: Ensures all `$ref` URLs are accessible and valid
- **Field type validation**: Validates field types and constraints
- **Required field validation**: Ensures required fields are properly defined

### UI Validation
- **Field consistency**: Ensures UI field definitions match JSON schema properties
- **Section validation**: Validates section structure and field references
- **Choice validation**: Ensures choice field configurations are valid

### Error Categories
- **Validation errors**: Schema structure and format issues
- **Reference errors**: Unresolvable `$ref` URLs
- **Rendering errors**: Issues during schema resolution
- **UI errors**: Interface definition problems

## Best Practices

### Schema Design
- **Use descriptive field names**: Follow consistent naming conventions
- **Provide clear titles and descriptions**: Help users understand field purposes
- **Set appropriate constraints**: Use min/max values, patterns, and required fields
- **Group related fields**: Use consistent prefixes for related fields

### Choice Management
- **Stable choice values**: Use URL-safe, stable values for choices
- **Meaningful display names**: Provide clear, localized display text
- **Document choice dependencies**: Keep track of which eventtypes use which choices
- **Version choice lists**: Plan for choice list updates and migrations

### UI Design
- **Logical field ordering**: Arrange fields in a logical workflow order
- **Responsive layouts**: Use appropriate column configurations for different screen sizes
- **Clear placeholders**: Provide helpful placeholder text for all fields
- **Accessibility**: Ensure proper labeling and keyboard navigation

### Performance
- **Minimize references**: Use local definitions when possible
- **Cache resolved schemas**: Implement caching for resolved choice references
- **Optimize choice lists**: Keep choice lists focused and relevant
- **Monitor resolution time**: Track reference resolution performance

## Troubleshooting

### Common Issues

#### Reference Resolution Failures
**Problem**: `$ref` URLs cannot be resolved
**Solution**:
- Verify API endpoints are accessible
- Check choice field names exist in the database
- Ensure proper authentication for API calls
- Test reference URLs manually

#### Schema Validation Errors
**Problem**: Schema fails JSON Schema validation
**Solution**:
- Use a JSON Schema validator to identify issues
- Check for missing required properties
- Verify field type definitions are correct
- Ensure `$ref` syntax is properly formatted

#### UI Rendering Issues
**Problem**: Fields not displaying correctly in the UI
**Solution**:
- Verify UI field definitions match JSON schema properties
- Check section structure and field references
- Ensure proper field types and input types
- Validate parent section references

#### Choice List Problems
**Problem**: Choice lists not populating or showing incorrect options
**Solution**:
- Verify choice records exist and are active
- Check choice field names match reference URLs
- Ensure choice API endpoints return proper format
- Test choice resolution independently

### Debugging Tips
1. **Validate schemas**: Use online JSON Schema validators
2. **Test references**: Manually test `$ref` URLs
3. **Check logs**: Review application logs for resolution errors
4. **Use development tools**: Leverage browser dev tools for UI issues
5. **Test incrementally**: Build and test schemas piece by piece

## Migration from V1

### Migration Process
1. **Analyze V1 schema**: Identify template variables and choice dependencies
2. **Convert to V2 format**: Replace templates with `$ref` references
3. **Update UI definition**: Convert custom definition format to V2 UI structure
4. **Test validation**: Ensure schemas validate correctly
5. **Update version**: Set `version = "2"` in the EventType model

### Migration Tools
- **Schema converter**: Automated tools for converting V1 to V2
- **Validation scripts**: Test converted schemas before deployment
- **Choice migration**: Tools for updating choice references
- **UI converter**: Convert V1 definition format to V2 UI structure

For detailed migration guidance, see the [V1 to V2 Migration Guide](./eventtype_migration.md).
