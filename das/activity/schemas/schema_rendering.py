import hashlib
import logging
from typing import Any, Union
from urllib.parse import urldefrag, urljoin

from referencing import Registry, Resource
from referencing import exceptions as referencing_exceptions
from referencing._core import Resolver
from referencing.jsonschema import DRAFT202012
from referencing.typing import URI

from activity.exceptions import SchemaRenderingError

logger = logging.getLogger(__name__)


def hash_base_uri(uri: URI) -> str:
    """Generates an short hash? from a URI"""
    md5_hash = hashlib.md5(uri.encode())
    return md5_hash.hexdigest()[:8]


class SchemaRenderer:
    """
    Partial dereferencing of schemas, using a registry as a reference resolver.

    The dereferencing process is a bit tricky, it's not possible to remove all references, as:
    - Some references may be not resolvable or bad formed
    - Some references may be circular
    - We may not really want to "de-reference" all? what if we are pointing to a local local fragment?

    So the approach in a nutshell is to:
    - Output a valid and as self-contained as possible schema
    - Expand resolvable references to full URIs where possible.
    - Bundle resolvable references to fragments in nested schemas into $defs in the root schema
    - Rename anchor references in nested schemas to avoid collisions
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
        self.resolver = None

    def render(self, schema: Union[Resource, dict]) -> dict:
        """Unified entry point for rendering the schema"""
        try:
            return self._render(schema)
        except Exception as e:
            logger.error("Schema rendering failed: %s", str(e), exc_info=True)
            raise SchemaRenderingError(f"Failed to render schema: {e}") from e

    def get_set_bundle_defs(self, base_uri: str, fragment_uri: str, contents: dict) -> str:
        """
        Bundles the referenced fragment in the root $defs and returns the new local uri (#/$defs/hash/fragment).
        """
        hash_uri = hash_base_uri(base_uri)
        local_uri = fragment_uri.lstrip("#/")
        local_uri_bits = local_uri.split("/")
        if len(local_uri_bits) > 1:
            # Usually the first part is the $defs key, should be safe to remove it
            local_uri_bits.pop(0)
        local_uri = "-".join(local_uri_bits)

        if hash_uri not in self.bundled_defs:
            self.bundled_defs[hash_uri] = {}
        if local_uri not in self.bundled_defs[hash_uri]:
            self.bundled_defs[hash_uri][local_uri] = contents

        return f"#/$defs/{hash_uri}/{local_uri}"

    @staticmethod
    def get_anchor_name(base_uri: str, anchor_fragment: str) -> str:
        """
        Anchors are names for a specific location in a document.
        While traversing the schemas we might find already used anchor names by other schemas, to avoid collisions we
        will generate a new anchor name.

        Returns the an updated anchor uri, using the base uri
        """
        hash_uri = hash_base_uri(base_uri)
        return f"#{hash_uri}-{anchor_fragment}"

    def get_resolver_for(self, resource: Resource) -> Resolver:
        resource_id = resource.id() or ""
        if resource_id and resource_id not in self.registry:
            resolver = self.registry.resolver_with_root(resource)
            self.registry = resolver._registry
        resolver = self.registry.resolver(base_uri=resource_id)
        return resolver

    def _render(self, schema: Union[Resource, dict]) -> dict:
        if isinstance(schema, dict):
            schema = Resource.from_contents(contents=schema, default_specification=DRAFT202012)

        self.bundled_defs = {}
        self.resolver = self.get_resolver_for(schema)
        root_uri = schema.id() or ""
        # We'll track "currently visiting" URIs with a stack.
        active_uris = []

        def dereference(value: Any, current_uri: str) -> Any:
            if isinstance(value, dict):
                new_dict = {**value}

                if current_uri != root_uri and "$id" in new_dict:
                    # we are at the root a nested schema
                    new_dict.pop("$schema", None)
                    new_dict.pop("$id", None)

                    # removing these ones here means that "sub-references" inside will not be resolved, just "bundled"
                    new_dict.pop("$defs", None)
                    new_dict.pop("$definitions", None)

                # We'll expand everything else inside:
                resolved_dict = {}
                if "$ref" in new_dict:
                    ref_uri = new_dict.pop("$ref")
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
                                new_dict["$ref"] = ref_uri
                            elif fragment.startswith("/"):
                                # local reference in a nested schema => bundle it into $defs
                                resolved = self.resolver.lookup(retrieve_ref_uri)
                                self.resolver = resolved.resolver
                                new_ref_uri = self.get_set_bundle_defs(retrieve_uri, fragment, resolved.contents)
                                new_dict["$ref"] = new_ref_uri
                            else:
                                # anchor reference in a nested schema => rename it (to avoid collisions)
                                new_dict["$ref"] = self.get_anchor_name(retrieve_uri, fragment)

                        else:
                            # full URI with no fragment => let's try to expand it!
                            if retrieve_uri in active_uris:
                                # circular reference => leave it as is
                                new_dict["$ref"] = retrieve_uri
                                logger.info(f"Circular reference: {retrieve_uri}")
                                return new_dict

                            resolved = self.resolver.lookup(retrieve_uri)
                            self.resolver = resolved.resolver

                            # ID defined in the schema => Is the base that the schema uses to resolve
                            # relative references, from the schema's perspective.
                            next_uri = resolved.contents.get("$id", retrieve_uri)
                            active_uris.append(retrieve_uri)
                            resolved_dict = dereference(resolved.contents, next_uri)
                            active_uris.pop()

                    except referencing_exceptions.Unresolvable as e:
                        # leave it as $ref if we can't resolve it
                        logger.info("Unresolvable reference %s => %s", ref_uri, str(e))
                        new_dict["$ref"] = ref_uri

                if "$anchor" in new_dict:
                    # let's generate a collision free version
                    new_dict["$anchor"] = self.get_anchor_name(current_uri, new_dict["$anchor"])

                for k, v in new_dict.items():
                    if k in ("$ref", "$anchor"):
                        continue
                    new_dict[k] = dereference(v, current_uri)

                # If we have a resolved reference, let's merge it with the current value
                if resolved_dict:
                    new_dict = {**resolved_dict, **new_dict}

                return new_dict

            elif isinstance(value, list):
                return [dereference(v, current_uri) for v in value]
            else:
                return value

        # Update registry after dereferencing
        self.registry = self.resolver._registry

        # Start dereferencing from the root
        active_uris.append(root_uri)
        full_schema = dereference(schema.contents, root_uri)
        active_uris.pop()  # active_uris should be empty now...

        if self.bundled_defs:
            if "$defs" not in full_schema:
                full_schema["$defs"] = self.bundled_defs
            else:
                full_schema["$defs"].update(self.bundled_defs)

        return full_schema
