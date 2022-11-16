from typing import Dict, Tuple

import pytest
from referencing import Registry

from activity.schemas.schema_rendering import SchemaRenderer

from .helpers import get_counting_retriever
from .schema_examples import BASE_URL, SAMPLE_SCHEMAS


def call_count_schema_renderer() -> Tuple[SchemaRenderer, Dict[str, int]]:
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)
    return renderer, call_counts


def test_no_references():
    """
    If there's no '$ref' in the schema, SchemaRenderer should not modify anything.
    And the retriever shouldn't be called.
    """
    renderer, call_counts = call_count_schema_renderer()

    output = renderer.dereference_schema(SAMPLE_SCHEMAS["sample_event_type.json"])
    assert output == SAMPLE_SCHEMAS["sample_event_type.json"]
    assert not call_counts, "No fetches expected if there's no references ($ref)"


def test_local_fragment_reference():
    """
    A local reference inside the same schema (#/definitions/something).
    Check that if it's resolvable at the root, it's left as is.
    """
    schema = {
        "$id": f"{BASE_URL}/local_fragment_referencing.json",
        "type": "object",
        "custom_definitions": {"foo": {"type": "string"}},
        "properties": {
            "bar": {"$ref": "#/custom_definitions/foo"},
        },
    }
    renderer, call_counts = call_count_schema_renderer()

    output = renderer.dereference_schema(schema)
    # It's a root-level reference, should be keeped as defined
    assert output["properties"]["bar"]["$ref"] == "#/custom_definitions/foo"
    # And no external fetches
    assert not call_counts, "No fetches expected if there's no references ($ref)"


def test_full_uri_reference():
    """
    A full URI reference should be resolved and the fragment bundled.
    The 'fire_event.json' schema has a reference to the 'status_options.json' schema and a local fragment reference.
    """
    renderer, call_counts = call_count_schema_renderer()

    output = renderer.dereference_schema(SAMPLE_SCHEMAS["fire_event.json"])

    status_prop = output["properties"]["status"]
    expected_keys = ["title", "type", "oneOf"]
    not_expected_keys = ["$ref", "$id", "$schema"]

    # Check expected keys
    for key in expected_keys:
        assert key in status_prop, f"Expected key {key} not found in status property"

    # Check not expected keys
    for key in not_expected_keys:
        assert key not in status_prop, f"Unexpected key {key} found in status property"

    # We should have 1 fetch call (status_options.json)
    assert len(call_counts.keys()) == 1, f"Expected 1 fetch call, got {len(call_counts.keys())}"

    # Verify fetched URI
    expected_uri = f"{BASE_URL}/status_options.json"
    assert expected_uri in call_counts, f"Expected fetch for {expected_uri} was not made"
    assert call_counts[expected_uri] == 1, f"Expected exactly one fetch for {expected_uri}"

    # Verify local fragment reference is left as is
    assert output["properties"]["suspected_cause_type"]["$ref"] == "#/$defs/cause_types"


def test_full_uri_reference_overrides():
    """
    If a full URI reference has at the same level other properties defined, those properties should override the ones
    defined in the referenced schema.
    """
    renderer, call_counts = call_count_schema_renderer()

    schema = {
        "$id": f"{BASE_URL}/extra_properties.json",
        "type": "object",
        "properties": {
            "foo": {
                "$ref": f"{BASE_URL}/health_status_options.json",
                "title": "Health Status",
                "type": "integer",
            },
            "bar": {"type": "string"},
        },
    }
    output = renderer.dereference_schema(schema)
    assert "oneOf" in output["properties"]["foo"], "Expected to see health_status_options expanded after dereferencing"
    assert len(output["properties"]["foo"]["oneOf"]) == 4
    assert output["properties"]["foo"]["title"] == "Health Status"  # the value we provided
    assert output["properties"]["foo"]["type"] == "integer"

    # Verify that the health_status_options.json was fetched
    assert call_counts == {f"{BASE_URL}/health_status_options.json": 1}


def test_full_uri_reference_overrides_in_definitions():
    """
    If a full URI reference appears in the definitions, that reference should be expanded/dereferenced the same way
    as other full URI references.

    The 'full_uri_ref_in_defs.json' schema references the 'status_options.json' schema in the definitions.

    This is an interesting one, it shows the case of a having a reference to a "local resource", but the
    definition of that resource is another full uri reference to an external resource, and it gets fully expanded,
    this can be usefull for many scenarios.
        - Having to mention multiple times a reference, in the same schema but to an external resource,
          this would allow to generate smaller schemas
        - Having an external resource that is referenced in multiple schemas like the one described before,
          this would allow keep all those in sync with the changes in the shared external resource. etc.
    """
    renderer, call_counts = call_count_schema_renderer()

    schema = SAMPLE_SCHEMAS["full_uri_ref_in_defs.json"]
    output = renderer.dereference_schema(schema)

    # Verify that status_options was fetched and expanded in the definitions
    assert "oneOf" in output["$defs"]["status_options"]
    assert len(output["$defs"]["status_options"]["oneOf"]) == 4

    # Verify that only one fetch was made for status_options.json
    assert len(call_counts.keys()) == 2
    expected_uris = [f"{BASE_URL}/status_options.json", f"{BASE_URL}/fire_event.json"]
    for uri in expected_uris:
        assert uri in call_counts
        assert call_counts[uri] == 1

    # Verify that the local reference to the definition is preserved
    assert output["properties"]["status"]["$ref"] == "#/$defs/status_options"

    # Verify that the external fragment reference is bundled properly
    assert "cause_types" in output["properties"]
    assert output["properties"]["cause_types"]["$ref"].startswith("#/$defs/")


def test_external_fragment_reference():
    """
    A fragment reference to an external schema should be resolved and the fragment bundled.
    The 'external_fragment_ref.json' schema references the 'cause_types' fragment from 'fire_event.json'.
    """
    renderer, _ = call_count_schema_renderer()
    output = renderer.dereference_schema(SAMPLE_SCHEMAS["external_fragment_ref.json"])

    assert "$ref" in output["properties"]["cause_types"]
    bundled_ref = output["properties"]["cause_types"]["$ref"]
    assert bundled_ref.startswith("#/$defs/"), f"The expected path should begin with `$defs`, got {bundled_ref}"

    def_path = bundled_ref.lstrip("#/").split("/")
    bundled_def = output
    for path_part in def_path:
        assert path_part in bundled_def, "No valid path for bundled reference"
        bundled_def = bundled_def[path_part]

    # Verify the bundled definition matches the original from fire_event.json
    original_cause_types = SAMPLE_SCHEMAS["fire_event.json"]["$defs"]["cause_types"]
    assert "type" in bundled_def
    assert bundled_def["type"] == original_cause_types["type"]
    assert "enum" in bundled_def
    assert set(bundled_def["enum"]) == set(original_cause_types["enum"])


def test_external_fragment_reference_in_definitions():
    """
    A fragment reference to an external schema defined in definitions should be resolved and the fragment bundled.
    The 'external_fragment_ref_in_defs.json' schema references the 'cause_types' fragment from 'fire_event.json'.
    """
    renderer, _ = call_count_schema_renderer()
    output = renderer.dereference_schema(SAMPLE_SCHEMAS["external_fragment_ref_in_defs.json"])

    assert "$ref" in output["properties"]["cause_types"]
    original_ref = output["properties"]["cause_types"]["$ref"]
    assert original_ref.startswith("#/$defs/"), f"The expected path should begin with `$defs`, got {original_ref}"

    def_path = original_ref.lstrip("#/").split("/")
    bundled_def = output
    for path_part in def_path:
        assert path_part in bundled_def, "No valid path for bundled reference"
        bundled_def = bundled_def[path_part]

    bundled_ref = bundled_def["$ref"]
    def_path = bundled_ref.lstrip("#/").split("/")
    bundled_def = output
    for path_part in def_path:
        assert path_part in bundled_def, "No valid path for bundled reference"
        bundled_def = bundled_def[path_part]

    # Verify the bundled definition matches the original from fire_event.json
    original_cause_types = SAMPLE_SCHEMAS["fire_event.json"]["$defs"]["cause_types"]
    assert "type" in bundled_def
    assert bundled_def["type"] == original_cause_types["type"]
    assert "enum" in bundled_def
    assert set(bundled_def["enum"]) == set(original_cause_types["enum"])


def test_local_fragment_reference_not_resolvable():
    """
    A local reference inside the same schema (#/definitions/something).
    Check that if it's not resolvable at the root, it's left as is.
    Just because some versions of renderer where removing the $ref key.
    """
    renderer, call_counts = call_count_schema_renderer()

    schema = {
        "$id": f"{BASE_URL}/local_fragment_referencing.json",
        "type": "object",
        "custom_definitions": {"foo": {"type": "string"}},
        "properties": {"bar": {"$ref": "#/custom_definitions/baz"}},
    }
    output = renderer.dereference_schema(schema)
    # It's a root-level reference, should be keeped as defined
    assert output["properties"]["bar"]["$ref"] == "#/custom_definitions/baz"
    # And no external fetches
    assert not call_counts


@pytest.mark.skip(reason="Temporary override to avoid failure on FE validation")
def test_external_fragment_reference_not_resolvable():
    """
    A fragment reference from an external schema should be left as is if
    it's not resolvable.

    Here we can have two cases, one is that the resource is resolvable, but the fragment is not.
    The other is that the resource is not resolvable.
    """
    # Case 1: Resource exists but fragment doesn't
    schema = {
        "$id": f"{BASE_URL}/external_fragment_reference.json",
        "type": "object",
        "properties": {
            "cause_types": {"$ref": f"{BASE_URL}/fire_event.json#/$defs/nonexistent"},
        },
    }

    renderer, call_counts = call_count_schema_renderer()
    output = renderer.dereference_schema(schema)

    # Check that the unresolvable reference is left as is
    assert output["properties"]["cause_types"]["$ref"] == f"{BASE_URL}/fire_event.json#/$defs/nonexistent"

    # Verify that the fire_event.json was fetched
    assert f"{BASE_URL}/fire_event.json" in call_counts
    assert call_counts[f"{BASE_URL}/fire_event.json"] == 1

    # Case 2: Resource doesn't exist
    nonexistent_schema_uri = f"{BASE_URL}/nonexistent_schema.json"
    schema = {
        "$id": f"{BASE_URL}/external_fragment_reference2.json",
        "type": "object",
        "properties": {
            "some_property": {"$ref": f"{nonexistent_schema_uri}#/$defs/something"},
        },
    }

    renderer, call_counts = call_count_schema_renderer()
    output = renderer.dereference_schema(schema)

    # Check that the unresolvable reference is left as is
    assert output["properties"]["some_property"]["$ref"] == f"{nonexistent_schema_uri}#/$defs/something"

    # Verify that an attempt was made to fetch the nonexistent schema
    assert nonexistent_schema_uri in call_counts
    assert call_counts[nonexistent_schema_uri] == 1


@pytest.mark.skip(reason="Temporary override to avoid failure on FE validation")
def test_unresolvable_reference_left_as_is():
    """
    If a schema references something that doesn't exist in local_schemas,
    it remains a $ref unmodified.
    """
    renderer, call_counts = call_count_schema_renderer()
    missing_schema_uri = f"{BASE_URL}/missing_schema.json"
    schema = {"$id": f"{BASE_URL}/unknown_ref.json", "$ref": missing_schema_uri}
    output = renderer.dereference_schema(schema)

    # The code tries to fetch, fails, so it leaves the $ref as was defined
    assert output["$ref"] == missing_schema_uri
    # And we do record that one retrieval attempt:
    assert call_counts[missing_schema_uri] == 1


def test_not_resolved_reference_is_replaced_by_empty_object():
    """
    If a schema references something that can not be resolved/fetched,
    it is replaced by an empty object.
    """
    renderer, call_counts = call_count_schema_renderer()
    missing_schema_uri = f"{BASE_URL}/missing_schema.json"
    schema = {"$id": f"{BASE_URL}/unknown_ref.json", "$ref": missing_schema_uri}
    output = renderer.dereference_schema(schema)

    # The code tries to fetch, fails, so it replaces the $ref with an empty object
    assert "$ref" not in output
    assert "oneOf" in output
    assert len(output["oneOf"]) == 0
    assert "type" in output
    assert output["type"] == "string"

    # And we do record that one retrieval attempt:
    assert call_counts[missing_schema_uri] == 1


def test_nested_references():
    """
    Test a schema with multiple nested references to ensure they're all properly dereferenced.
    """
    renderer, call_counts = call_count_schema_renderer()
    nested_schema = SAMPLE_SCHEMAS["nested_references.json"]
    output = renderer.dereference_schema(nested_schema)

    # Check that the nested references were dereferenced
    assert "oneOf" in output["properties"]["status"]
    assert "properties" in output["properties"]["fire_event"]
    assert "properties" in output["properties"]["animal_event"]

    # Check that status has been dereferenced for fire_event and animal_event
    assert "oneOf" in output["properties"]["fire_event"]["properties"]["status"]
    assert "oneOf" in output["properties"]["animal_event"]["properties"]["status"]

    # We should have exactly 5 fetch calls
    assert len(call_counts) == 5

    expected_uris = [
        f"{BASE_URL}/status_options.json",
        f"{BASE_URL}/fire_event.json",
        f"{BASE_URL}/animal_event.json",
        f"{BASE_URL}/health_status_options.json",
        f"{BASE_URL}/dead_reason_options.json",
    ]

    for uri in expected_uris:
        assert uri in call_counts, f"Expected fetch for {uri} was not made"
        assert call_counts[uri] == 1


def test_local_anchor_references():
    """
    Test that anchor references are handled correctly by the SchemaRenderer.

    This test verifies that:
    1. Root-level anchor references are kept intact (not modified)
    2. Nested anchor references from external schemas are renamed for collision avoidance

    Note:
    This test does not verify that the anchor references are resolved correctly,
    The bundling for the case of anchors is not currently implemented.
    """
    # Create a schema with root-level anchors
    schema_with_anchors = {
        "$id": f"{BASE_URL}/SchemaWithAnchors.json",
        "type": "object",
        "$defs": {
            "string_type": {"$anchor": "string-type", "type": "string"},
            "number_type": {"$anchor": "number-type", "type": "number"},
        },
        "properties": {
            "root_string_ref": {"$ref": "#string-type"},  # Root-level anchor reference
            "root_number_ref": {"$ref": "#number-type"},  # Root-level anchor reference
        },
    }

    # Create a schema that references external anchors
    referencing_schema = {
        "$id": f"{BASE_URL}/ReferencingSchema.json",
        "type": "object",
        "properties": {
            "nested_string_ref": {"$ref": f"{BASE_URL}/SchemaWithAnchors.json#string-type"},
            "nested_number_ref": {"$ref": f"{BASE_URL}/SchemaWithAnchors.json#number-type"},
        },
    }

    # Map schema names to schema objects for the retriever
    local = {"SchemaWithAnchors.json": schema_with_anchors, "ReferencingSchema.json": referencing_schema}

    retriever, _ = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    # Test root-level anchor references (in the same document)
    root_output = renderer.dereference_schema(schema_with_anchors)

    # Root anchor references should remain unchanged
    assert (
        root_output["properties"]["root_string_ref"]["$ref"] == "#string-type"
    ), "Root-level anchor reference should not be modified"
    assert (
        root_output["properties"]["root_number_ref"]["$ref"] == "#number-type"
    ), "Root-level anchor reference should not be modified"

    # Test nested anchor references (from another document)
    nested_output = renderer.dereference_schema(referencing_schema)

    # Nested anchor references should be renamed to avoid collisions
    string_ref = nested_output["properties"]["nested_string_ref"]["$ref"]
    number_ref = nested_output["properties"]["nested_number_ref"]["$ref"]

    # References should be modified to match the SchemaRenderer.get_anchor_name pattern
    assert string_ref.startswith("#"), "Anchor reference should start with #"
    assert "-string-type" in string_ref, "Anchor reference should contain the original anchor name"
    assert string_ref != "#string-type", "Anchor reference should be modified to avoid collisions"

    assert number_ref.startswith("#"), "Anchor reference should start with #"
    assert "-number-type" in number_ref, "Anchor reference should contain the original anchor name"
    assert number_ref != "#number-type", "Anchor reference should be modified to avoid collisions"

    # Both references to anchors in the same external schema should have the same hash prefix
    string_prefix = string_ref.split("-string-type")[0]
    number_prefix = number_ref.split("-number-type")[0]
    assert string_prefix == number_prefix, "References to the same schema should share the same hash prefix"


def test_uris_retrieved_only_once():
    """
    Test that a full URI reference should be retrieved only once.
    If a schema with an id is provided, it should become part of the `registry` being used to resolve references.

    First fire_event.json:
    Is passed and rendered, then status_options.json is retrieved and cached along with fire_event.json

    Then animal_event.json:
    Is passed and rendered, then health_status_options.json and dead_reason_options.json are retrieved and cached.
    But status_options.json is already cached, so it is not retrieved again.

    Then nested_references.json:
    Is passed and rendered, at this point all the schemas are already cached. No additional fetches are expected.
    """
    renderer, call_counts = call_count_schema_renderer()

    # URIs of the schemas
    status_options_uri = f"{BASE_URL}/status_options.json"
    health_status_options_uri = f"{BASE_URL}/health_status_options.json"
    dead_reason_options_uri = f"{BASE_URL}/dead_reason_options.json"

    # fire_event.json references status_options.json
    renderer.dereference_schema(SAMPLE_SCHEMAS["fire_event.json"])
    assert status_options_uri in call_counts, f"Expected fetch for {status_options_uri} was not made"
    assert call_counts[status_options_uri] == 1

    # animal_event.json references status_options.json, health_status_options.json and dead_reason_options.json
    renderer.dereference_schema(SAMPLE_SCHEMAS["animal_event.json"])
    assert call_counts[status_options_uri] == 1  # Still 1, already cached
    assert call_counts[health_status_options_uri] == 1
    assert call_counts[dead_reason_options_uri] == 1

    # nested_references.json references status_options.json, fire_event.json and animal_event.json
    renderer.dereference_schema(SAMPLE_SCHEMAS["nested_references.json"])
    assert call_counts[status_options_uri] == 1
    assert call_counts[health_status_options_uri] == 1
    assert call_counts[dead_reason_options_uri] == 1
    assert len(call_counts) == 3, f"Expected 3 fetch calls, got {len(call_counts)}"


def test_circular_reference():
    """
    Create 2 schemas that reference each other, ensure no infinite recursion
    and see how partial expansion works.
    """
    # We'll add these 2 to the local dictionary
    schema_a = {"$id": f"{BASE_URL}/A.json", "type": "object", "properties": {"b_ref": {"$ref": f"{BASE_URL}/B.json"}}}
    schema_b = {"$id": f"{BASE_URL}/B.json", "type": "object", "properties": {"a_ref": {"$ref": f"{BASE_URL}/A.json"}}}
    local = {
        "A.json": schema_a,
        "B.json": schema_b,
    }
    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.dereference_schema(schema_a)
    # Typically you'd see partial expansion of B inside A, but then B points back to A =>
    # it remains a $ref to avoid infinite recursion or references the top-level ID.
    b_prop = output["properties"]["b_ref"]
    assert "properties" in b_prop
    assert b_prop["properties"]["a_ref"]["$ref"] == f"{BASE_URL}/A.json", "Circular fallback"

    # Confirm we fetched B once
    full_b_uri = f"{BASE_URL}/B.json"
    assert call_counts[full_b_uri] == 1
    assert len(call_counts) == 1


def test_complex_circular_reference():
    """
    Test a more complex circular reference chain: A -> B -> C -> A.
    Ensures that the renderer correctly handles multi-step circular references.
    """
    # Create schemas with a three-way circular reference
    schema_a = {"$id": f"{BASE_URL}/A.json", "type": "object", "properties": {"b_ref": {"$ref": f"{BASE_URL}/B.json"}}}
    schema_b = {"$id": f"{BASE_URL}/B.json", "type": "object", "properties": {"c_ref": {"$ref": f"{BASE_URL}/C.json"}}}
    schema_c = {"$id": f"{BASE_URL}/C.json", "type": "object", "properties": {"a_ref": {"$ref": f"{BASE_URL}/A.json"}}}

    local = {
        "A.json": schema_a,
        "B.json": schema_b,
        "C.json": schema_c,
    }

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.dereference_schema(schema_a)

    # Verify B was expanded
    b_prop = output["properties"]["b_ref"]
    assert "properties" in b_prop, "B should be expanded"

    # Verify C was expanded inside B
    c_prop = b_prop["properties"]["c_ref"]
    assert "properties" in c_prop, "C should be expanded"

    # Verify the circular reference back to A is maintained as a $ref
    a_ref = c_prop["properties"]["a_ref"]
    assert "$ref" in a_ref, "Reference back to A should be preserved"
    assert a_ref["$ref"] == f"{BASE_URL}/A.json", "A reference should point to original A"

    # Verify all schemas were fetched exactly once
    assert call_counts[f"{BASE_URL}/B.json"] == 1, "B should be fetched once"
    assert call_counts[f"{BASE_URL}/C.json"] == 1, "C should be fetched once"


def test_self_reference():
    """
    Test a schema that references itself.
    This tests proper handling of direct self-references.
    """
    # Create a schema that references itself
    self_schema = {
        "$id": f"{BASE_URL}/Self.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child": {"$ref": f"{BASE_URL}/Self.json"}},  # Self-reference
    }

    local = {"Self.json": self_schema}
    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.dereference_schema(self_schema)

    # Verify the self-reference is maintained
    child_prop = output["properties"]["child"]
    assert "$ref" in child_prop, "Self-reference should be preserved"
    assert child_prop["$ref"] == f"{BASE_URL}/Self.json", "Self-reference should point to the original schema"

    # Verify the schema was fetched at most once (might not fetch at all if handling via ID)
    assert call_counts.get(f"{BASE_URL}/Self.json", 0) <= 1, "Self schema should be fetched at most once"


def test_nested_circular_references():
    """
    Test how the SchemaRenderer handles nested circular references in a more complex schema structure.

    This test creates a parent-child structure with two circular reference patterns:
    - Parent schema references two children (ChildA and ChildB)
    - ChildA references ChildB
    - ChildB references ChildA

    The test verifies that:
    1. First-level references (Parent->ChildA, Parent->ChildB) are fully expanded
    2. Second-level references (ChildA->ChildB, ChildB->ChildA) are also expanded, no circular references yet
    3. Third-level references that would create circular loops (ChildB->ChildA->ChildB,
       ChildA->ChildB->ChildA) are preserved as $ref (without expansion)

    Proper management of the stack of schemas being processed is required to avoid infinite recursion or
    false detection of cycles.
    """
    # Create schemas with nested circular references
    parent = {
        "$id": f"{BASE_URL}/Parent.json",
        "type": "object",
        "properties": {"child_a": {"$ref": f"{BASE_URL}/ChildA.json"}, "child_b": {"$ref": f"{BASE_URL}/ChildB.json"}},
    }
    child_a = {
        "$id": f"{BASE_URL}/ChildA.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child_b_ref": {"$ref": f"{BASE_URL}/ChildB.json"}},
    }
    child_b = {
        "$id": f"{BASE_URL}/ChildB.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child_a_ref": {"$ref": f"{BASE_URL}/ChildA.json"}},
    }

    local = {
        "Parent.json": parent,
        "ChildA.json": child_a,
        "ChildB.json": child_b,
    }

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.dereference_schema(parent)

    # Get the expanded child schemas
    child_a_prop = output["properties"]["child_a"]
    child_b_prop = output["properties"]["child_b"]

    # 1. Verify top-level expansion
    assert "properties" in child_a_prop, "ChildA should be expanded"
    assert "properties" in child_b_prop, "ChildB should be expanded"

    # 2. Verify circular references are expanded one level deep
    # Check ChildA -> ChildB reference
    child_b_ref = child_a_prop["properties"]["child_b_ref"]
    assert "properties" in child_b_ref, "ChildB reference should be expanded"

    # Check ChildB -> ChildA reference
    child_a_ref = child_b_prop["properties"]["child_a_ref"]
    assert "properties" in child_a_ref, "ChildA reference should be expanded"

    # 3. Verify circular references are preserved at the second level
    # ChildA -> ChildB -> ChildA (should be a $ref)
    assert "$ref" in child_b_ref["properties"]["child_a_ref"]
    assert child_b_ref["properties"]["child_a_ref"]["$ref"] == f"{BASE_URL}/ChildA.json"

    # ChildB -> ChildA -> ChildB (should be a $ref)
    assert "$ref" in child_a_ref["properties"]["child_b_ref"]
    assert child_a_ref["properties"]["child_b_ref"]["$ref"] == f"{BASE_URL}/ChildB.json"

    # 4. Verify each schema was fetched exactly once
    assert call_counts[f"{BASE_URL}/ChildA.json"] == 1
    assert call_counts[f"{BASE_URL}/ChildB.json"] == 1
    assert len(call_counts) == 2


def test_fragment_circular_reference():
    """
    Test circular references involving schema fragments across different files.

    This test verifies that:
    1. Fragments in external resources (FragmentB.json#/$defs/item) are correctly bundled
       into the root schema's $defs rather than expanded inline
    2. The original fragment reference is replaced with a local reference to the bundled fragment
    3. When fragments contain circular references back to the original schema,
       these references are preserved as $ref to avoid infinite recursion

    The reference pattern is:
    - FragmentA references FragmentB.json#/$defs/item
    - FragmentB#/$defs/item references back to FragmentA

    The SchemaRenderer should handle this by:
    - Bundling the fragment from B into A's $defs
    - Preserving the circular reference back to A as a $ref
    """
    # Create schemas with fragment references that form a circular reference
    fragment_a = {
        "$id": f"{BASE_URL}/FragmentA.json",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "b_fragment_ref": {"$ref": f"{BASE_URL}/FragmentB.json#/$defs/item"},
        },
    }
    fragment_b = {
        "$id": f"{BASE_URL}/FragmentB.json",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "$defs": {
            "item": {
                "type": "object",
                "properties": {"a_ref": {"$ref": f"{BASE_URL}/FragmentA.json"}},
            },
        },
    }

    local = {"FragmentA.json": fragment_a, "FragmentB.json": fragment_b}

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    # Render FragmentA (the schema that contains the fragment reference)
    output = renderer.dereference_schema(fragment_a)

    # Verify that the fragment reference is bundled into the output's $defs
    assert "$defs" in output, "The rendered schema should include $defs for bundled fragments"

    # Get the hash ID generated for the bundled fragment
    assert len(output["$defs"]) == 1, "Should have exactly one bundled fragment"
    hash_id = list(output["$defs"].keys())[0]

    assert "item" in output["$defs"][hash_id], "The bundled fragment should contain the 'item' from FragmentB"

    # Verify the fragment reference is replaced with a local reference
    b_fragment_ref = output["properties"]["b_fragment_ref"]
    assert "$ref" in b_fragment_ref, "Fragment reference should be replaced with a local reference"
    assert b_fragment_ref["$ref"] == f"#/$defs/{hash_id}/item", "Fragment reference should point to bundled fragment"

    # Verify the bundled fragment contains the expected content
    bundled_fragment = output["$defs"][hash_id]["item"]
    assert "properties" in bundled_fragment, "Bundled fragment should contain properties"
    assert "a_ref" in bundled_fragment["properties"], "Bundled fragment should contain the a_ref property"

    # Verify the circular reference back to A is preserved as a $ref to avoid infinite recursion
    a_ref = bundled_fragment["properties"]["a_ref"]
    assert "$ref" in a_ref, "Reference back to A should be preserved as $ref"
    assert a_ref["$ref"] == f"{BASE_URL}/FragmentA.json", "A reference should point to original A"

    # Verify all schemas were fetched exactly once
    assert call_counts[f"{BASE_URL}/FragmentB.json"] == 1, "FragmentB should be fetched once"
    assert call_counts.get(f"{BASE_URL}/FragmentA.json", 0) == 0, "FragmentA shouldn't be fetched"
