def humanize_field_name(text: str) -> str:
    if text == "reported_by_id":
        return "Reported by"
    return text.replace("_", " ").capitalize()
