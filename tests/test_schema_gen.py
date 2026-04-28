from halflist.schema_gen import generate_args


def test_string_type():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    assert generate_args(schema) == {"name": "test"}


def test_integer_type():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    assert generate_args(schema) == {"count": 0}


def test_number_type():
    schema = {"type": "object", "properties": {"value": {"type": "number"}}}
    assert generate_args(schema) == {"value": 0.0}


def test_boolean_type():
    schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}}
    assert generate_args(schema) == {"flag": True}


def test_string_with_enum():
    schema = {"type": "object", "properties": {"color": {"type": "string", "enum": ["red", "blue"]}}}
    assert generate_args(schema) == {"color": "red"}


def test_string_with_format_uri():
    schema = {"type": "object", "properties": {"url": {"type": "string", "format": "uri"}}}
    assert generate_args(schema) == {"url": "https://example.com"}


def test_string_with_format_email():
    schema = {"type": "object", "properties": {"email": {"type": "string", "format": "email"}}}
    assert generate_args(schema) == {"email": "test@example.com"}


def test_nested_object():
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                "required": ["name"],
            }
        },
    }
    assert generate_args(schema) == {"user": {"name": "test"}}


def test_empty_schema():
    assert generate_args({}) == {}
    assert generate_args(None) == {}  # type: ignore[arg-type]


def test_const_value():
    schema = {"type": "object", "properties": {"version": {"const": "1.0"}}}
    assert generate_args(schema) == {"version": "1.0"}


def test_default_value():
    schema = {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}
    assert generate_args(schema) == {"limit": 10}


def test_required_only():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name"],
    }
    result = generate_args(schema)
    assert "name" in result
    assert "age" not in result


def test_array_type():
    schema = {"type": "object", "properties": {"items": {"type": "array"}}}
    assert generate_args(schema) == {"items": []}


def test_integer_with_minimum():
    schema = {"type": "object", "properties": {"count": {"type": "integer", "minimum": 5}}}
    assert generate_args(schema) == {"count": 5}


def test_string_with_min_length():
    schema = {"type": "object", "properties": {"code": {"type": "string", "minLength": 10}}}
    result = generate_args(schema)
    assert len(result["code"]) >= 10
