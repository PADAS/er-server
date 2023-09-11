import json
import logging
from functools import wraps
from typing import Union

from utils.features import features
from utils.tenant.managers import TenantContextManager

logger = logging.getLogger(__name__)


def append_domain_to_message(message: Union[dict, str], domain: str) -> Union[dict, str]:
    if isinstance(message, dict):
        message["domain"] = domain
        return message

    elif isinstance(message, str):
        message = json.loads(message)
        message["domain"] = domain
        return json.dumps(message)

    else:
        raise Exception("message should be dict or str")


def wrap_message_processing_with_tenant_context(message_handler):
    """Wraps the message handler function, to setup the Tenant
    context manager from the message.

    Args:
        message_handler : the message handler function to wrap

    Returns:
        a pointer to the wrapped function
    """

    @wraps(message_handler)
    def wrapper(*args, **kwargs):
        if not features.tms.is_on():
            return message_handler(*args, **kwargs)

        if "domain" not in args[0]:
            logger.warning("Tenant Domain not found in PubSub message %s %s", str(args), str(kwargs))
            return

        domain = args[0].pop("domain")
        with TenantContextManager(domain):
            return message_handler(*args, **kwargs)

    return wrapper
