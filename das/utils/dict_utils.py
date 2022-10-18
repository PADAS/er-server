""" Utilities for working with dictionaries. """


def get_nested_value(data: dict, path: str, default=None):
    """
    Get a value from a dictionary using a dot-separated path.

    Args:
        data (dict): The dictionary to search.
        path (str): The path to the value, separated by dots.
        default: The default value to return if the path is not found.

    Returns:
        The value at the path, or the default value if not found.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
