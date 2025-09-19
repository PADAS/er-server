import re
from typing import Callable, Union


def replace_template_vars(template: str, replace_with: Union[Callable[[str], str], str]) -> str:
    """
    Replace template variables ({{var_name}}) in a string with specified values.

    Args:
        template: String containing template variables in {{var_name}} format
        replace_with: Either a string to replace all variables with the same value,
                     or a callable that takes the variable name and returns the replacement

    Returns:
        String with all template variables replaced

    Examples:
        >>> replace_template_vars("Hello {{name}}", "World")
        'Hello World'

        >>> replace_template_vars("{{x}} + {{y}}", lambda var: "1" if var == "x" else "2")
        '1 + 2'
    """
    pattern = r"\{\{[^}]+\}\}"

    if callable(replace_with):

        def replacer(match: re.Match) -> str:
            var_name = match.group(0)[2:-2]  # Extract content between {{ and }}
            return replace_with(var_name)

        return re.sub(pattern, replacer, template)

    return re.sub(pattern, replace_with, template)


def humanize_field_name(text: str) -> str:
    if text == "reported_by_id":
        return "Reported by"
    return text.replace("_", " ").capitalize()
