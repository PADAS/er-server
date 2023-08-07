import json
from typing import Union


def append_domain_into_message(message: Union[dict, str], domain: str) -> Union[dict, str]:
    if isinstance(message, dict):
        message["domain"] = domain
        return message

    elif isinstance(message, str):
        message = json.loads(message)
        message["domain"] = domain
        return json.dumps(message)

    else:
        raise Exception("message should be dict or str")
