import hashlib
import logging
from typing import Any, Union
from urllib.parse import urldefrag, urljoin

from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions
from referencing.jsonschema import DRAFT202012
from referencing.typing import URI

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


def dereference_schema(schema: Union[Resource, dict], registry: Registry) -> dict:
    """
    Renders/Dereferences a schema, using a registry as a reference resolver.

    The dereferencing process is a bit tricky, it's not possible to remove all references, as:
    - Some references may be not resolvable
        - A reference that points to a place that does not exist or to a not existing anchor
        - At the moment the retriever does not support external references
        - The aproach is to fail "gracefully" and leave the references that can not be resolved as is
    - Some references may be circular (we can't resolve them, as soon as we find them we just fallback to the reference)
    - We may not really want to "de-reference" all? what if we are pointing to a local local fragment?

    So the approach in a nutshell is:
    - To output a valid and as self-contained as possible schema
    - Partial derreferencing, we will dereference only the references that are resolvable
    - Fragments will be bundled in the root schema, instead of being dereferenced

    In detail:
    - We traverse the schema
    - When a reference is found, we determine if it's a local reference or not.
        - If it's fragment (#/) reference, we just make sure that is resolvable
            - If it's resolvable, and we are at the root level, we leave it as is
            - If it's resolvable, and we are not at the root level, we bundle it in the "$defs" key of the root schema
            - If it's not resolvable, we leave it as is
        - If it's an anchor reference, we generate a collision free anchor name version
        - If it's a full uri reference, we retrieve it and dereference it
    """
    root_uri = "/"
    traversed_uris = set()

    if isinstance(schema, dict):
        schema = Resource.from_contents(contents=schema, default_specification=DRAFT202012)
        if schema_id := schema.id():
            root_uri = schema_id

    registry = registry.with_resource(uri=root_uri, resource=schema)
    resolver = registry.resolver_with_root(schema)
    bundled_defs = {}

    def _get_set_bundle_defs(base_uri: str, fragment_uri: str, contents: dict) -> str:
        """
        Bundles it in the $defs key of the root schema and returns the new local uri for the fragment.
        Why?:
        - Local references may be used multiple times and in different schemas
        - If we are using local references in our schemas, there should be a reason for it
        - We need to keep the references in the context of the root schema
        - We want to avoid key collisions
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

    def _dereference(value: Any, current_uri: str) -> dict:
        nonlocal resolver  # we need to update the resolver in the parent scope

        if isinstance(value, dict):
            # Handle $id to update current_uri for this scope
            if "$id" in value:
                # check for fragment in the uri and remove it?
                current_uri = value["$id"]
                if current_uri != root_uri:
                    # we are in a nested schema, we need to bundle the local references in the root schema
                    value.pop("$schema", None)
                    value.pop("$id", None)
                    value.pop("$defs", None)  # we don't need them in nested schemas
                    value.pop("$definitions", None)

                if current_uri in traversed_uris and len(traversed_uris) > 1:
                    # we are in a circular reference, let's fallback to the reference, to avoid infinite recursion
                    logger.info(f"Circular reference detected for schema: {current_uri}")
                    return {"$ref": current_uri}
                traversed_uris.add(current_uri)

            resolved_value = {}
            if "$ref" in value:
                ref_uri = value.pop("$ref")
                retrieve_ref_uri = ref_uri
                if ref_uri.startswith("#"):
                    # it's a local reference, let's build the full uri for the resolver to find it
                    retrieve_ref_uri = urljoin(current_uri, ref_uri)

                retrieve_uri, fragment = urldefrag(retrieve_ref_uri)
                try:
                    if fragment:
                        # it's a fragment reference
                        if retrieve_uri == root_uri:
                            # it's a local reference at the root level, we leave it as is
                            value["$ref"] = ref_uri
                        elif fragment.startswith("/"):
                            # it's a local reference in a nested schema, we bundle it in the root schema
                            resolved = resolver.lookup(retrieve_ref_uri)
                            resolver = resolved.resolver
                            new_ref_uri = _get_set_bundle_defs(retrieve_uri, fragment, resolved.contents)
                            value["$ref"] = new_ref_uri
                        else:
                            # it's an anchor reference, let's generate a collision free anchor name version
                            value["$ref"] = _get_anchor_name(retrieve_uri, fragment)
                    else:
                        # it's a full uri reference, retrieve and dereference it!
                        resolved = resolver.lookup(ref_uri)
                        resolver = resolved.resolver
                        resolved_value = _dereference(resolved.contents, current_uri)
                except referencing_exceptions.Unresolvable as e:
                    # leave the reference as is
                    value["$ref"] = ref_uri
                    logger.info(f"Unresolvable reference: {e}")
            if "$anchor" in value:
                # defines an anchor, let's generate a collision free version
                value["$anchor"] = _get_anchor_name(current_uri, value["$anchor"])

            value = {k: _dereference(v, current_uri) for k, v in value.items()}
            if resolved_value:
                # we have a resolved reference, let's merge it with the current value
                value = {**resolved_value, **value}
            return value
        elif isinstance(value, list):
            return [_dereference(v, current_uri) for v in value]
        else:
            return value

    full_schema = _dereference(schema.contents, root_uri)

    if bundled_defs:
        if "$defs" not in full_schema:
            full_schema["$defs"] = bundled_defs
        else:
            full_schema["$defs"].update(bundled_defs)

    return full_schema
