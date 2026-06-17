from __future__ import annotations

import re

from django.urls import reverse


def slugify_for_choice(value: str) -> str:
    """Convert a string to a valid choice field name (lowercase, underscores only)."""
    slugified = value.lower()
    slugified = re.sub(r"[^a-z0-9]+", "_", slugified)
    slugified = re.sub(r"_+", "_", slugified)
    return slugified.strip("_")


def smart_abbreviate(text: str, max_length: int = 40) -> str:
    """
    Abbreviates a snake_case string to fit within max_length by:
    1. Removing vowels from words (except the first letter).
    2. Strict truncation if still too long.
    """
    if len(text) <= max_length:
        return text

    parts = text.split("_")

    def drop_vowels(word: str) -> str:
        if not word:
            return word
        first = word[0]
        rest = re.sub(r"[aeiou]", "", word[1:])
        return first + rest

    abbrev_parts = [drop_vowels(p) for p in parts]
    new_text = "_".join(abbrev_parts)

    if len(new_text) <= max_length:
        return new_text

    # Still too long, strictly truncate and clean up trailing underscores
    return new_text[:max_length].rstrip("_")


def rewrite_field_to_ref(field_schema: dict, choice_field_name: str) -> None:
    """Replace hardcoded anyOf/oneOf with a $ref to the choices endpoint. Mutates in-place."""
    ref_url = f"{reverse('schemas:choices')}?field={choice_field_name}"  # reverse() is cached by Django
    field_schema["anyOf"] = [{"$ref": ref_url}]
