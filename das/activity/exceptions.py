SCHEMA_ERROR_INCORRECT_RENDER_TAG = "Incorrect event render tag, tag should " \
                                    "be in the form 'xxx___xxx___xxx'"
SCHEMA_ERROR_JSON_DECODE_ERROR = "Schema can not be decoded"

SCHEMA_ERROR_EMPTY_PROPERTY = "Each property must contain at minimum a type and a title"

SCHEMA_ERROR_MISMATCHED_PROPERTIES_IN_DEFINITION = "Some property keys missing in the definition"


class SchemaValidationError(Exception):
    pass
