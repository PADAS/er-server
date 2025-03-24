from referencing import Resource
from referencing import exceptions as referencing_exceptions
from referencing.jsonschema import DRAFT202012


def get_counting_retriever(base_url: str, local_schemas: dict):
    """
    Returns (retriever, call_counts).
      - retriever is a callable the referencing Registry uses to fetch schemas.
      - call_counts is a dict that records how many times each URI is fetched.
    """
    call_counts = {}

    def counting_retriever(uri: str) -> Resource:
        # Bump the counter
        call_counts[uri] = call_counts.get(uri, 0) + 1

        # The "file name" is everything after base_url, might be 'event_types/status_options.json', etc.
        if uri.startswith(base_url):
            path = uri[len(base_url) :].lstrip("/")
            if path in local_schemas:
                schema_dict = local_schemas[path]
                return Resource.from_contents(schema_dict, default_specification=DRAFT202012)

        # If we can't match, we consider it unresolvable
        raise referencing_exceptions.Unresolvable(ref=uri)

    return counting_retriever, call_counts
