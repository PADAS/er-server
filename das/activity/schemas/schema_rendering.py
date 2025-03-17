import hashlib
import logging
from typing import Any, Union
from urllib.parse import urldefrag, urljoin

from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions
from referencing.jsonschema import DRAFT202012
from referencing.typing import URI

from activity.exceptions import SchemaRenderingError

logger = logging.getLogger(__name__)


def _hash_base_uri(uri: URI) -> str:
    """Generates an short hash? from a URI"""
    md5_hash = hashlib.md5(uri.encode())
    return md5_hash.hexdigest()[:8]


def _get_anchor_name(base_uri: str, anchor_fragment: str) -> str:
    """
    Anchors are names for a specific location in a document.
    While traversing the schemas we might find already used anchor names by other schemas, to avoid collisions we will
    generate a new anchor name.

    Returns the an updated anchor uri, using the base uri
    """
    hash_uri = _hash_base_uri(base_uri)
    return f"#{hash_uri}-{anchor_fragment}"


class SchemaRenderer:
    """
    Partial dereferencing of schemas, using a registry as a reference resolver.

    The dereferencing process is a bit tricky, it's not possible to remove all references, as:
    - Some references may be not resolvable or bad formed
    - Some references may be circular
    - We may not really want to "de-reference" all? what if we are pointing to a local local fragment?

    So the approach in a nutshell is to:
    - Output a valid and as self-contained as possible schema
    - Expand resolvable references where possible.
    - Bundle local fragments from nested schemas into $defs
    - Leave unresolvable references as-is.

    In detail:
    - We traverse the schema
    - When a reference is found
        - If it's fragment (#/) reference
            - If it's local and we are at the root level, we leave it as is
            - If it's resolvable, and we are not at the root level
                - We retrieve it and we bundle it in the "$defs" key of the root schema
            - If it's not resolvable, we leave it as is
        - If it's an anchor reference, and we are not at the root level
            -  We generate a collision free anchor name version
        - If it's a full uri reference:
            - We try to retrieve it and dereference (expand) it
            - If it's not resolvable, we leave it as is
            - If it's a circular reference, we fallback to the reference and leave it as is
    """

    def __init__(self, registry: Registry):
        self.registry = registry

    def render(self, schema: Union[Resource, dict]) -> dict:
        """Unified entry point for rendering the schema"""
        try:
            return self._render(schema)
        except Exception as e:
            logger.error(f"Schema rendering failed: {e}", exc_info=True)
            raise SchemaRenderingError(f"Failed to render schema: {e}") from e

    def _render(self, schema: Union[Resource, dict]) -> dict:

        if isinstance(schema, dict):
            schema = Resource.from_contents(contents=schema, default_specification=DRAFT202012)

        root_uri = schema.id() or "/root/"
        resolver = self.registry.resolver_with_root(schema)
        bundled_defs = {}
        # We'll track "currently visiting" URIs with a stack.
        active_uris = []

        def _get_set_bundle_defs(base_uri: str, fragment_uri: str, contents: dict) -> str:
            """
            Bundles the referenced fragment in the root $defs and returns the new local uri (#/$defs/hash/fragment).
            """
            hash_uri = _hash_base_uri(base_uri)
            local_uri = fragment_uri.lstrip("#/")
            local_uri_bits = local_uri.split("/")
            if len(local_uri_bits) > 1:
                # Usually the first part is the $defs key, should be safe to remove it
                local_uri_bits.pop(0)
            local_uri = "-".join(local_uri_bits)

            if hash_uri not in bundled_defs:
                bundled_defs[hash_uri] = {}
            if local_uri not in bundled_defs[hash_uri]:
                bundled_defs[hash_uri][local_uri] = contents

            return f"#/$defs/{hash_uri}/{local_uri}"

        def _dereference(value: Any, current_uri: str) -> Any:
            nonlocal resolver  # so we can update the resolver whenever we resolve a reference

            if isinstance(value, dict):
                if "$id" in value:
                    new_id = value["$id"]
                    if new_id in active_uris:
                        logger.info(f"Circular reference detected for schema: {new_id}")
                        # Return a $ref pointing to that $id as a fallback.
                        return {"$ref": new_id}

                    if new_id != root_uri:
                        # we are in a nested schema => need to bundle the local references in the root schema
                        value.pop("$schema", None)
                        value.pop("$id", None)

                        # removing these ones means that "sub-references" inside will not be resolved
                        value.pop("$defs", None)
                        value.pop("$definitions", None)

                # We'll expand everything else inside:
                resolved_value = {}
                if "$ref" in value:
                    ref_uri = value.pop("$ref")
                    retrieve_ref_uri = ref_uri
                    if ref_uri.startswith("#"):
                        # it's a local fragment => build the full uri for the resolver to find it
                        retrieve_ref_uri = urljoin(current_uri, ref_uri)

                    retrieve_uri, fragment = urldefrag(retrieve_ref_uri)
                    try:
                        if fragment:
                            # it's something like ...#/someFragment
                            if retrieve_uri == root_uri:
                                # local reference at the root level => leave it as is
                                value["$ref"] = ref_uri
                            elif fragment.startswith("/"):
                                # local reference in a nested schema => bundle it into $defs
                                resolved = resolver.lookup(retrieve_ref_uri)
                                resolver = resolved.resolver
                                new_ref_uri = _get_set_bundle_defs(retrieve_uri, fragment, resolved.contents)
                                value["$ref"] = new_ref_uri
                            else:
                                # anchor reference in a nested schema => rename it (to avoid collisions)
                                value["$ref"] = _get_anchor_name(retrieve_uri, fragment)

                        else:
                            # full URI with no fragment => let's try to expand it!
                            if retrieve_uri in active_uris:
                                # circular reference => leave it as is
                                value["$ref"] = retrieve_uri
                                logger.info(f"Circular reference: {retrieve_uri}")
                                return value

                            resolved = resolver.lookup(retrieve_uri)
                            resolver = resolved.resolver

                            next_uri = resolved.contents.get("$id", retrieve_uri)
                            active_uris.append(retrieve_uri)

                            resolved_value = _dereference(resolved.contents, next_uri)
                            active_uris.pop()

                    except referencing_exceptions.Unresolvable as e:
                        # leave it as $ref if we can't resolve it
                        logger.info(f"Unresolvable reference {ref_uri} => {e}")
                        value["$ref"] = ref_uri

                if "$anchor" in value:
                    # let's generate a collision free version
                    value["$anchor"] = _get_anchor_name(current_uri, value["$anchor"])

                # Recurse into subkeys
                new_dict = {}
                for k, v in value.items():
                    new_dict[k] = _dereference(v, current_uri)

                # If we have a resolved reference, let's merge it with the current value
                if resolved_value:
                    new_dict = {**resolved_value, **new_dict}

                return new_dict

            elif isinstance(value, list):
                return [_dereference(v, current_uri) for v in value]
            else:
                return value

        # Start dereferencing from the root
        active_uris.append(root_uri)
        full_schema = _dereference(schema.contents, root_uri)
        active_uris.pop()  # active_uris should be empty now...

        if bundled_defs:
            if "$defs" not in full_schema:
                full_schema["$defs"] = bundled_defs
            else:
                full_schema["$defs"].update(bundled_defs)

        return full_schema
