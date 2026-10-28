"""Every query parameter in the API schema says what it does.

62 had no description. Most were the shared listing parameters, now described
from their own schema by ``app.openapi_docs`` (so the stated bounds cannot drift
from the validator); the rest — the calendar window, ``platforms``, ``q``,
``refresh``, … — are described at the route. This keeps the next one from
arriving undocumented.
"""
from __future__ import annotations

from app.openapi_docs import describe_common_parameters


def test_every_query_parameter_has_a_description(client):
    spec = client.get("/openapi.json").json()
    missing = [
        f"{method.upper()} {path} ?{parameter['name']}"
        for path, operations in spec["paths"].items()
        for method, operation in operations.items()
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query" and not parameter.get("description")
    ]
    assert not missing, "\n".join(missing)


def test_generated_descriptions_state_the_real_bounds(client):
    spec = client.get("/openapi.json").json()
    params = {p["name"]: p for p in spec["paths"]["/api/v1/content"]["get"]["parameters"]}
    assert params["limit"]["description"] == "Most items to return (1–500, default 100)."
    assert "skip" in params["offset"]["description"]


def test_a_route_written_description_is_never_overwritten():
    schema = {
        "paths": {
            "/x": {"get": {"parameters": [
                {"in": "query", "name": "limit", "description": "Hand-written.", "schema": {}},
            ]}}
        }
    }
    describe_common_parameters(schema)
    assert schema["paths"]["/x"]["get"]["parameters"][0]["description"] == "Hand-written."
