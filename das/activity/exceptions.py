from django.utils.translation import gettext_lazy as _

SCHEMA_ERROR_INCORRECT_RENDER_TAG = _("Incorrect event render tag, tag should " "be in the form 'xxx___xxx___xxx'")
SCHEMA_ERROR_JSON_DECODE_ERROR = _("Schema can not be decoded")

SCHEMA_ERROR_EMPTY_PROPERTY = _("Each property must contain at minimum a type and a title")

SCHEMA_ERROR_MISSING_DOLLAR_SIGN_SCHEMA = _('schema must contain the "$schema" keyword')


class SchemaValidationError(Exception):
    pass


class SchemaRenderingError(SchemaValidationError):
    pass


class UnmappableFormKeyError(SchemaValidationError):
    pass


# ---------------------------------------------------------------------------
# Dynamic schema retrieval exceptions (for activity.schemas.schema_retrieving)
# ---------------------------------------------------------------------------


class SchemaRetrievalError(Exception):
    """Base exception for errors during dynamic schema retrieval."""

    def __init__(self, message: str, *, uri: str):
        super().__init__(message)
        self.uri = uri  # The reference URI associated with the failure


class UnresolvableUri(SchemaRetrievalError):
    """Raised when the URI cannot be resolved by any resolver."""


class UriIsNotJsonSchema(SchemaRetrievalError):
    """Raised when the retrieved URI is not a JSON schema."""


class UriNotFound(SchemaRetrievalError):
    """Raised when the resolver gets a 404 when retrieving the URI."""


class HttpError(SchemaRetrievalError):
    """Raised when the HTTP request to retrieve the URI fails."""
