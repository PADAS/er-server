from django.utils.translation import ugettext_lazy as _

SCHEMA_ERROR_INCORRECT_RENDER_TAG = _("Incorrect event render tag, tag should " \
                                    "be in the form 'xxx___xxx___xxx'")
SCHEMA_ERROR_JSON_DECODE_ERROR = _("Schema can not be decoded")

SCHEMA_ERROR_EMPTY_PROPERTY = _("Each property must contain at minimum a type and a title")

SCHEMA_ERROR_MISMATCHED_PROPERTIES_IN_DEFINITION = _("Some property keys missing in the definition")


class SchemaValidationError(Exception):
    pass
