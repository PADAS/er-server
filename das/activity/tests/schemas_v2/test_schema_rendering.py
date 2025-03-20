from referencing import Registry

from activity.schemas.schema_rendering import SchemaRenderer

from .schema_examples import BASE_URL, SAMPLE_SCHEMAS
from .test_helpers import get_counting_retriever


def test_no_references():
    """
    If there's no '$ref' in the schema, SchemaRenderer should not modify anything.
    And the retriever shouldn't be called.
    """
    schema = {"$id": f"{BASE_URL}/no_refs.json", "type": "object", "properties": {"foo": {"type": "string"}}}
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(schema)
    assert output == schema
    assert call_counts == {}, "No fetches expected if there's no references ($ref)"


def test_local_fragment_reference():
    """
    A local reference inside the same schema (#/definitions/something).
    Check that if it's resolvable at the root, it's left as is.
    """
    schema = {
        "$id": f"{BASE_URL}/local_fragment_referencing.json",
        "type": "object",
        "custom_definitions": {"foo": {"type": "string"}},
        "properties": {"bar": {"$ref": "#/custom_definitions/foo"}},
    }
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(schema)
    # It's a root-level reference, should be keeped as defined
    assert output["properties"]["bar"]["$ref"] == "#/custom_definitions/foo"
    # And no external fetches
    assert call_counts == {}


def test_full_uri_reference():
    """
    A full URI reference should be resolved and the fragment bundled.
    The 'fire_event.json' schema has a reference to the 'status_options.json' schema and a local fragment reference.
    """
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(SAMPLE_SCHEMAS["fire_event.json"])

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
    assert len(call_counts.keys()) == 1

    # Verify fetched URI
    expected_uri = f"{BASE_URL}/status_options.json"
    assert expected_uri in call_counts, f"Expected fetch for {expected_uri} was not made"
    assert call_counts[expected_uri] == 1, f"Expected exactly one fetch for {expected_uri}"

    # Verify local fragment reference is left as is
    assert output["properties"]["suspected_cause_type"]["$ref"] == "#/$defs/cause_types"


def test_uris_retrieved_only_once():
    """
    A full URI reference should be retrieved only once, if we are rendering multiple schemas, all the references should be fetched only once.
    """
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    renderer.render(SAMPLE_SCHEMAS["fire_event.json"])  # fire_event.json references status_options.json
    renderer.render(SAMPLE_SCHEMAS["animal_event.json"])  # animal_event.json references status_options.json
    renderer.render(
        SAMPLE_SCHEMAS["nested_references.json"]
    )  # nested_references.json references status_options.json, fire_event.json and animal_event.json

    assert len(call_counts.keys()) == 3

    # Verify fetched URIs
    expected_uris = [f"{BASE_URL}/status_options.json", f"{BASE_URL}/fire_event.json", f"{BASE_URL}/animal_event.json"]
    for uri in expected_uris:
        assert uri in call_counts, f"Expected fetch for {uri} was not made"
        assert call_counts[uri] == 1, f"Expected exactly one fetch for {uri}"


def test_full_uri_reference_overrides():
    """
    If a full URI reference has at the same level other properties defined, those properties should remain.
    """
    schema = {
        "$id": f"{BASE_URL}/extra_properties.json",
        "type": "object",
        "properties": {
            "foo": {"$ref": f"{BASE_URL}/health_status_options.json", "title": "Health Status", "type": "integer"},
            "bar": {"type": "string"},
        },
    }
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(schema)
    assert output["properties"]["foo"]["title"] == "Health Status"
    assert output["properties"]["foo"]["type"] == "integer"

    # Verify that the health_status_options.json was fetched
    assert call_counts == {f"{BASE_URL}/health_status_options.json": 1}


def test_external_fragment_reference():
    """
    A fragment reference to another schema should be resolved and the fragment bundled.
    The 'fragment_reference.json' schema references the 'cause_types' fragment from 'fire_event.json'.
    """
    fragment_schema = SAMPLE_SCHEMAS["fragment_reference.json"]
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(fragment_schema)

    # Check that the external fragment reference was properly resolved
    cause_categories = output["properties"]["cause_categories"]
    assert "enum" in cause_categories, "Expected to see the enum from fire_event.json's cause_types fragment"
    assert cause_categories["type"] == "string"
    assert set(cause_categories["enum"]) == {"fire", "flood", "earthquake", "storm"}

    # Verify the other reference was also resolved
    status_prop = output["properties"]["status"]
    assert "oneOf" in status_prop, "Expected to see inlined status_options after dereferencing"

    # We should have 2 fetch calls (fire_event.json and status_options.json)
    assert len(call_counts.keys()) == 2

    # Verify specific fetches
    expected_uris = [f"{BASE_URL}/fire_event.json", f"{BASE_URL}/status_options.json"]

    for uri in expected_uris:
        assert uri in call_counts, f"Expected fetch for {uri} was not made"
        assert call_counts[uri] == 1, f"Expected exactly one fetch for {uri}"


def test_local_fragment_reference_not_resolvable():
    """
    A local reference inside the same schema (#/definitions/something).
    Check that if it's not resolvable at the root, it's left as is.
    """
    schema = {
        "$id": f"{BASE_URL}/local_fragment_referencing.json",
        "type": "object",
        "custom_definitions": {"foo": {"type": "string"}},
        "properties": {"bar": {"$ref": "#/custom_definitions/baz"}},
    }
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(schema)
    # It's a root-level reference, should be keeped as defined
    assert output["properties"]["bar"]["$ref"] == "#/custom_definitions/baz"
    # And no external fetches
    assert call_counts == {}


def test_external_fragment_reference():
    """
    Here 'fire_event.json' references 'status_options.json' by full URI.
    It should be de-referenced, and exactly one fetch call to 'event_types/status_options.json'.
    """
    fire_event = SAMPLE_SCHEMAS["fire_event.json"]
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(fire_event)

    # The "status" property used to have a $ref to status_options.json
    status_prop = output["properties"]["status"]
    assert "oneOf" in status_prop, "Expected to see inlined status_options after dereferencing"

    # 'event_types/status_options.json' is the path portion
    assert len(call_counts) == 1
    fetch_uri = f"{BASE_URL}/status_options.json"
    assert fetch_uri in call_counts
    assert call_counts.pop(fetch_uri) == 1
    assert not call_counts, "No other fetches expected"


def test_fire_event_references_status_options():
    """
    Here 'fire_event.json' references 'status_options.json' by full URI.
    It should be de-referenced, and exactly one fetch call to 'status_options.json'.
    """
    fire_event = SAMPLE_SCHEMAS["fire_event.json"]
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(fire_event)

    # The "status" property used to have a $ref to status_options.json
    status_prop = output["properties"]["status"]
    assert "oneOf" in status_prop, "Expected to see inlined status_options after dereferencing"

    # 'event_types/status_options.json' is the path portion
    assert len(call_counts) == 1
    fetch_uri = f"{BASE_URL}/status_options.json"
    assert fetch_uri in call_counts
    assert call_counts.pop(fetch_uri) == 1
    assert not call_counts, "No other fetches expected"


def test_nested_references():
    """
    Test a schema with multiple nested references to ensure they're all properly dereferenced.
    """
    nested_schema = SAMPLE_SCHEMAS["nested_references.json"]
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(nested_schema)

    # Check that the nested references were resolved
    assert "title" in output["properties"]["event"]
    assert "oneOf" in output["properties"]["status"]
    assert "properties" in output["properties"]["animal_data"]

    # We should have 4 fetch calls (fire_event, status_options, animal_event, and health_status_options)
    # dead_reason_options might not be fetched because it's conditionally required
    assert len(call_counts) >= 4

    # Verify specific fetches
    expected_uris = [
        f"{BASE_URL}/fire_event.json",
        f"{BASE_URL}/status_options.json",
        f"{BASE_URL}/animal_event.json",
        f"{BASE_URL}/health_status_options.json",
    ]

    for uri in expected_uris:
        assert uri in call_counts, f"Expected fetch for {uri} was not made"


def test_fire_event_local_definition():
    """
    'fire_event.json' also references '#/$defs/cause_types' inside itself.
    We expect that to be left as is if resolvable at the root or possibly moved to $defs if it's nested.
    """
    fire_event = SAMPLE_SCHEMAS["fire_event.json"]
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(fire_event)
    # cause_types was a local definition, should be kept as is
    cause_ref = output["properties"]["suspected_cause_type"]
    assert "$ref" in cause_ref


def test_unresolvable_reference_left_as_is():
    """
    If a schema references something that doesn't exist in local_schemas,
    it remains a $ref unmodified.
    """
    schema = {"$id": f"{BASE_URL}/unknown_ref.json", "$ref": f"{BASE_URL}/event_types/missing_schema.json"}
    retriever, call_counts = get_counting_retriever(BASE_URL, SAMPLE_SCHEMAS)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(schema)

    # The code tries to fetch, fails, so it leaves the $ref alone
    assert output["$ref"] == f"{BASE_URL}/event_types/missing_schema.json"
    # And we do record that one retrieval attempt:
    attempted_uri = f"{BASE_URL}/event_types/missing_schema.json"
    assert call_counts[attempted_uri] == 1


def test_circular_reference():
    """
    Create 2 schemas that reference each other, ensure no infinite recursion
    and see how partial expansion works.
    """
    # We'll add these 2 to the local dictionary
    A = {"$id": f"{BASE_URL}/A.json", "type": "object", "properties": {"b_ref": {"$ref": f"{BASE_URL}/B.json"}}}
    B = {"$id": f"{BASE_URL}/B.json", "type": "object", "properties": {"a_ref": {"$ref": f"{BASE_URL}/A.json"}}}
    local = {
        "A.json": A,
        "B.json": B,
    }
    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(A)
    # Typically you'd see partial expansion of B inside A, but then B points back to A =>
    # it remains a $ref to avoid infinite recursion or references the top-level ID.
    b_prop = output["properties"]["b_ref"]
    assert "properties" in b_prop, "Likely partially expanded B"
    assert b_prop["properties"]["a_ref"]["$ref"] == f"{BASE_URL}/A.json", "Circular fallback"

    # Confirm we fetched B once
    full_b_uri = f"{BASE_URL}/B.json"
    assert call_counts[full_b_uri] == 1


def test_complex_circular_reference():
    """
    Test a more complex circular reference chain: A -> B -> C -> A.
    Ensures that the renderer correctly handles multi-step circular references.
    """
    # Create schemas with a three-way circular reference
    A = {"$id": f"{BASE_URL}/A.json", "type": "object", "properties": {"b_ref": {"$ref": f"{BASE_URL}/B.json"}}}
    B = {"$id": f"{BASE_URL}/B.json", "type": "object", "properties": {"c_ref": {"$ref": f"{BASE_URL}/C.json"}}}
    C = {"$id": f"{BASE_URL}/C.json", "type": "object", "properties": {"a_ref": {"$ref": f"{BASE_URL}/A.json"}}}

    local = {
        "A.json": A,
        "B.json": B,
        "C.json": C,
    }

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(A)

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
    Self = {
        "$id": f"{BASE_URL}/Self.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child": {"$ref": f"{BASE_URL}/Self.json"}},  # Self-reference
    }

    local = {"Self.json": Self}
    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(Self)

    # Verify the self-reference is maintained
    child_prop = output["properties"]["child"]
    assert "$ref" in child_prop, "Self-reference should be preserved"
    assert child_prop["$ref"] == f"{BASE_URL}/Self.json", "Self-reference should point to the original schema"

    # Verify the schema was fetched at most once (might not fetch at all if handling via ID)
    assert call_counts.get(f"{BASE_URL}/Self.json", 0) <= 1, "Self schema should be fetched at most once"


def test_nested_circular_references():
    """
    Test nested circular references within a complex schema structure.
    """
    # Create schemas with nested circular references
    Parent = {
        "$id": f"{BASE_URL}/Parent.json",
        "type": "object",
        "properties": {"child_a": {"$ref": f"{BASE_URL}/ChildA.json"}, "child_b": {"$ref": f"{BASE_URL}/ChildB.json"}},
    }
    ChildA = {
        "$id": f"{BASE_URL}/ChildA.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child_b_ref": {"$ref": f"{BASE_URL}/ChildB.json"}},
    }
    ChildB = {
        "$id": f"{BASE_URL}/ChildB.json",
        "type": "object",
        "properties": {"name": {"type": "string"}, "child_a_ref": {"$ref": f"{BASE_URL}/ChildA.json"}},
    }

    local = {"Parent.json": Parent, "ChildA.json": ChildA, "ChildB.json": ChildB}

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(Parent)

    # Verify Child A and Child B are expanded at the top level
    child_a_prop = output["properties"]["child_a"]
    child_b_prop = output["properties"]["child_b"]
    assert "properties" in child_a_prop, "ChildA should be expanded"
    assert "properties" in child_b_prop, "ChildB should be expanded"

    # Verify the circular references are preserved
    child_b_ref_in_a = child_a_prop["properties"]["child_b_ref"]
    child_a_ref_in_b = child_b_prop["properties"]["child_a_ref"]

    assert "$ref" in child_b_ref_in_a or "$id" in child_b_ref_in_a, "Reference to ChildB should be preserved"
    assert "$ref" in child_a_ref_in_b or "$id" in child_a_ref_in_b, "Reference to ChildA should be preserved"

    # Verify each schema was fetched exactly once
    assert call_counts[f"{BASE_URL}/ChildA.json"] == 1, "ChildA should be fetched once"
    assert call_counts[f"{BASE_URL}/ChildB.json"] == 1, "ChildB should be fetched once"


def test_fragment_circular_reference():
    """
    Test circular references involving schema fragments.
    """
    # Create schemas with fragment references that form a circular reference
    FragmentA = {
        "$id": f"{BASE_URL}/FragmentA.json",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "b_fragment_ref": {"$ref": f"{BASE_URL}/FragmentB.json#/$defs/item"},
        },
    }
    FragmentB = {
        "$id": f"{BASE_URL}/FragmentB.json",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "$defs": {"item": {"type": "object", "properties": {"a_ref": {"$ref": f"{BASE_URL}/FragmentA.json"}}}},
    }

    local = {"FragmentA.json": FragmentA, "FragmentB.json": FragmentB}

    retriever, call_counts = get_counting_retriever(BASE_URL, local)
    registry = Registry(retrieve=retriever)
    renderer = SchemaRenderer(registry)

    output = renderer.render(FragmentA)

    # Verify the fragment reference is expanded
    b_fragment_ref = output["properties"]["b_fragment_ref"]
    assert "properties" in b_fragment_ref, "Fragment from B should be expanded"

    # Verify the circular reference back to A is preserved
    a_ref = b_fragment_ref["properties"]["a_ref"]
    assert "$ref" in a_ref, "Reference back to A should be preserved"
    assert a_ref["$ref"] == f"{BASE_URL}/FragmentA.json", "A reference should point to original A"

    # Verify all schemas were fetched exactly once
    assert call_counts[f"{BASE_URL}/FragmentB.json"] == 1, "FragmentB should be fetched once"
