from app.services.funnel_testimonials import _testimonial_output_schema


def test_testimonials_openai_json_schema_required_lists_are_complete() -> None:
    schema = _testimonial_output_schema(1)
    items = schema["properties"]["testimonials"]["items"]
    meta = items["properties"]["meta"]
    reply = items["properties"]["reply"]

    # OpenAI strict JSON schema requires `required` for objects to include all keys in `properties`.
    assert set(schema["required"]) == set(schema["properties"].keys())
    assert set(items["required"]) == set(items["properties"].keys())
    assert set(meta["required"]) == set(meta["properties"].keys())
    assert set(reply["required"]) == set(reply["properties"].keys())

