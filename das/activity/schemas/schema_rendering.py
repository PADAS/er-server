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
    - Some references may be not resolvable or malformed
    - Some references may be circular
    - We may not really want to "de-reference" all, local fragments can be useful to reuse a definition
      in many parts of the same schema, helping also to keep the schema self-contained and not too large.

    So the approach in a nutshell is to:
    - Output a valid and as self-contained as possible schema
    - Expand resolvable references to full URIs where possible
    - Bundle resolvable fragment references into $defs in the root schema
    - Rename anchor references in nested schemas to avoid collisions
    - Leave unresolvable references as-is
    """

    def __init__(self, registry: Registry):
        self.registry = registry
        self.resolver = None
        self.bundled_defs = None
        self.active_uris = []
        self.root_uri = ""

    def dereference_schema(self, schema: Union[Resource, dict], base_uri: str = "") -> dict:
        """Unified entry point for partial dereferencing of schemas"""
        if isinstance(schema, dict):
            schema = Resource.from_contents(contents=schema, default_specification=DRAFT202012)

        self.bundled_defs = {}
        self.resolver = self.get_root_resolver(schema)
        self.root_uri = schema.id() or base_uri
        self.active_uris = []

        try:
            # Start dereferencing from the root
            self.active_uris.append(self.root_uri)
            full_schema = self.dereference(schema.contents, self.root_uri)
            self.active_uris.pop()  # active_uris should be empty now...

            # Add bundled definitions to the root schema
            if self.bundled_defs:
                full_schema.setdefault("$defs", {})
                full_schema["$defs"].update(self.bundled_defs)
            return full_schema
        except Exception as e:
            logger.error("Schema dereferencing failed: %s", str(e), exc_info=True)
            raise SchemaRenderingError(f"Failed to dereference schema: {e}") from e

    def dereference(self, value: Any, current_uri: str) -> Any:
        """
        Recursively processes the given schema value to handle JSON references and anchors.

        This method traverses the schema value, processing any `$ref` and `$anchor` keywords found.

        For dictionary values, it processes the dictionary and its sub-elements recursively.
        For list values, it processes each element recursively.
        For other types, it returns the value unchanged.

        :param value: The schema value to process.
        :param current_uri: The current base URI for resolving relative references.
        :return: The processed schema value.
        """
        if isinstance(value, dict):
            # copy the dictionary to avoid mutating the original
            new_dict = {**value}

            # if we're in a nested schema (not the root), remove root-level keys.
            if current_uri != self.root_uri and "$id" in new_dict:
                new_dict.pop("$schema", None)
                new_dict.pop("$id", None)
                # We will bundle $defs and $definitions from nested schemas into the root schema
                new_dict.pop("$defs", None)
                new_dict.pop("$definitions", None)

            # Process references and anchors
            dereferenced_dict = self.process_references(new_dict, current_uri)
            new_dict = self.process_anchors(new_dict, current_uri)

            # Recursively process sub-elements, skipping $ref and $anchor at this level
            for k, v in new_dict.items():
                if k in ("$ref", "$anchor"):
                    continue
                new_dict[k] = self.dereference(v, current_uri)

            # if we have a resolved reference, let's merge it with the current value
            if dereferenced_dict:
                new_dict = {**dereferenced_dict, **new_dict}
            return new_dict

        if isinstance(value, list):
            return [self.dereference(v, current_uri) for v in value]

        return value

    def process_references(self, node: dict, current_uri: str) -> Union[dict, None]:
        """
        Processes references on the provided node if any.

        :param node: The node to process, it will be modified in-place when it's about updating the reference.
        :param current_uri: The current URI of the node (used to resolve local references).
        :return: A dictionary that contains the resolved reference if it's resolvable, None otherwise.
        """
        if "$ref" not in node:
            return None

        ref_uri = node.pop("$ref")
        dereferenced_dict = {}

        full_ref_uri = ref_uri
        if ref_uri.startswith("#"):
            # it's a local fragment => build the full uri for the resolver to find it
            full_ref_uri = urljoin(current_uri, ref_uri)

        retrieve_uri, fragment = urldefrag(full_ref_uri)
        try:
            if fragment:
                # it's something like ...#/someFragment
                if retrieve_uri == self.root_uri:
                    # local reference at the root level => leave it as is
                    node["$ref"] = ref_uri
                elif fragment.startswith("/"):
                    # local reference in a nested schema => bundle it into $defs
                    resolved = self.resolve(full_ref_uri)
                    node["$ref"] = self.bundle_ref(retrieve_uri, fragment, resolved)
                else:
                    # anchor reference in a nested schema => rename it (to avoid collisions)
                    node["$ref"] = self.get_anchor_name(retrieve_uri, fragment)
            else:
                # full URI with no fragment => let's try to expand it!
                if retrieve_uri in self.active_uris:
                    # circular reference => leave it as is
                    node["$ref"] = retrieve_uri
                    logger.info("Circular reference: %s", retrieve_uri)
                else:
                    resolved = self.resolve(retrieve_uri)
                    # ID defined in the schema => Is the base that the schema uses to resolve
                    # relative references, from the schema's perspective.
                    next_uri = resolved.get("$id", retrieve_uri)
                    self.active_uris.append(retrieve_uri)
                    dereferenced_dict = self.dereference(resolved, next_uri)
                    self.active_uris.pop()

        except referencing_exceptions.Unresolvable as e:
            # leave it as $ref if we can't resolve it
            logger.info("Unresolvable reference %s => %s", ref_uri, str(e))
            node["$ref"] = ref_uri

        return dereferenced_dict

    def process_anchors(self, node: dict, current_uri: str) -> dict:
        """Processes anchors on the provided node if any."""
        if "$anchor" in node and current_uri != self.root_uri:
            # let's generate a collision free version
            node["$anchor"] = self.get_anchor_name(current_uri, node["$anchor"])

        return node

    def bundle_ref(self, base_uri: str, fragment_uri: str, contents: dict) -> str:
        """
        Bundles the referenced fragment into the root schema and returns the new local uri (#/$defs/hash/fragment).
        """
        hash_uri = hash_base_uri(base_uri)
        local_uri = fragment_uri.lstrip("#/")

        # e.g. remove the $defs key
        local_uri_bits = local_uri.split("/")
        if len(local_uri_bits) > 1:
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
        Generates a collision free anchor name.
        If it's a root level anchor, leaving it as where defined should not be a problem.
        If it's a nested anchor, we want to avoid collisions and generate a new anchor name.
        """
        hash_uri = hash_base_uri(base_uri)
        return f"#{hash_uri}-{anchor_fragment}"

    def get_root_resolver(self, resource: Resource) -> Resolver:
        """
        At the start of the rendering process of a schema, a new resolver should be created, if the provided schema
        has an $id, it will be used as the root URI.
        """
        resource_id = resource.id() or ""
        if resource_id and resource_id not in self.registry:
            resolver = self.registry.resolver_with_root(resource)
            self.registry = resolver._registry
        else:
            resolver = self.registry.resolver(base_uri=resource_id)
        return resolver

    def resolve(self, ref: URI) -> dict:
        """
        Looks up a reference using the current resolver.
        Makes sure we keep updated resolver and registry. Internally, 'referencing' lib evolves versions instead of
        mutating, so we have to update the resolver and registry manually.
        """
        resolved = self.resolver.lookup(ref)
        self.resolver = resolved.resolver
        self.registry = resolved.resolver._registry
        return resolved.contents
