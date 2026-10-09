"""Fail-closed JSON Schema subset used by Resolvent protocol 1.0.

No dependencies and no remote reference loading. Unsupported schema keywords
raise UnsupportedSchema; they never silently relax the authoritative schema.
This is intentionally not advertised as a general JSON Schema implementation.
"""
import datetime
import json
import math
import re


class Invalid(ValueError):
    pass


class UnsupportedSchema(Invalid):
    pass


SUPPORTED = {
    "$schema", "$id", "$ref", "$defs", "definitions", "title", "description",
    "$comment", "default", "examples", "type", "properties", "required",
    "additionalProperties", "items", "minItems", "maxItems", "uniqueItems",
    "minLength", "maxLength", "pattern", "format", "enum", "const", "anyOf",
    "oneOf", "allOf", "not", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minProperties", "maxProperties", "if", "then", "else"
}


def inspect_schema(schema):
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise UnsupportedSchema("Schema must be an object or boolean")
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise UnsupportedSchema("Unsupported schema keywords: " + ", ".join(sorted(unknown)))
    if "$ref" in schema and not schema["$ref"].startswith("#/"):
        raise UnsupportedSchema("Only local JSON Schema references are supported")
    if schema.get("format") not in (None, "date-time"):
        raise UnsupportedSchema("Unsupported schema format: " + str(schema["format"]))
    for key in ("properties", "$defs", "definitions"):
        for value in schema.get(key, {}).values():
            inspect_schema(value)
    for key in ("items", "additionalProperties", "not", "if", "then", "else"):
        if key in schema:
            inspect_schema(schema[key])
    for key in ("anyOf", "oneOf", "allOf"):
        for value in schema.get(key, []):
            inspect_schema(value)


def validate(value, schema, root=None, path="$", depth=0):
    if root is None:
        inspect_schema(schema)
        root = schema
    if depth > 120:
        raise Invalid("Schema/data nesting exceeds safety limit")
    if isinstance(schema, bool):
        if not schema:
            raise Invalid(path + ": disallowed value")
        return
    if "$ref" in schema:
        target = root
        try:
            for part in schema["$ref"][2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise UnsupportedSchema("Unresolved local schema reference") from None
        validate(value, target, root, path, depth + 1)
    types = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    if "type" in schema:
        wanted = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not all(t in types for t in wanted):
            raise UnsupportedSchema("Unsupported type")
        if not any(types[t] for t in wanted):
            raise Invalid(path + ": wrong type")
    canonical = lambda x: json.dumps(x, sort_keys=True, allow_nan=False)
    if "const" in schema and canonical(value) != canonical(schema["const"]):
        raise Invalid(path + ": const mismatch")
    if "enum" in schema and canonical(value) not in [canonical(x) for x in schema["enum"]]:
        raise Invalid(path + ": enum mismatch")
    def matches(s):
        try:
            validate(value, s, root, path, depth + 1)
            return True
        except UnsupportedSchema:
            raise
        except Invalid:
            return False
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            count = sum(matches(s) for s in schema[key])
            if (key == "anyOf" and count == 0) or (key == "oneOf" and count != 1) or (key == "allOf" and count != len(schema[key])):
                raise Invalid(path + ": " + key + " mismatch")
    if "not" in schema and matches(schema["not"]):
        raise Invalid(path + ": forbidden match")
    if "if" in schema:
        branch = "then" if matches(schema["if"]) else "else"
        if branch in schema:
            validate(value, schema[branch], root, path, depth + 1)
    if isinstance(value, dict):
        if set(schema.get("required", [])) - set(value):
            raise Invalid(path + ": missing required properties")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                validate(item, props[key], root, path + "." + key, depth + 1)
            elif "additionalProperties" in schema:
                validate(item, schema["additionalProperties"], root, path + "." + key, depth + 1)
        for key, good in (("minProperties", lambda n: len(value) >= n), ("maxProperties", lambda n: len(value) <= n)):
            if key in schema and not good(schema[key]):
                raise Invalid(path + ": " + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            raise Invalid(path + ": array length")
        if schema.get("uniqueItems") and len({canonical(x) for x in value}) != len(value):
            raise Invalid(path + ": duplicate array items")
        if "items" in schema:
            for i, item in enumerate(value):
                validate(item, schema["items"], root, path + "[" + str(i) + "]", depth + 1)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", math.inf):
            raise Invalid(path + ": string length")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise Invalid(path + ": pattern mismatch")
        if schema.get("format") == "date-time":
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})", value):
                    raise ValueError()
                parsed = datetime.datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
            except ValueError:
                raise Invalid(path + ": expected date-time with timezone") from None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for key, good in (("minimum", lambda n: value >= n), ("maximum", lambda n: value <= n), ("exclusiveMinimum", lambda n: value > n), ("exclusiveMaximum", lambda n: value < n)):
            if key in schema and not good(schema[key]):
                raise Invalid(path + ": " + key)
