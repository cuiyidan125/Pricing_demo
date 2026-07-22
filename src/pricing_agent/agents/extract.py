"""Natural language to validated JSON. §4.2.

Two layers of enforcement, deliberately:

1. **Structured outputs** constrain the model's response to the extraction schema below.
   That schema contains no computed field — no price, no valuation, no days-to-sale — so
   there is no property for a model to populate with an invented number.
2. **Local schema validation** then checks the assembled request against the real
   `single-vehicle-request.schema.json`. The model's output is a candidate; the schema
   decides whether it may reach a tool.

The extraction schema is a simplified mirror of the request schema rather than the schema
itself: structured outputs does not support `minimum`, `maximum`, `pattern`, or the other
constraints the real schema uses, and silently dropping them would leave the model's
contract quietly different from the one the system validates against.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from pricing_agent.config.loader import SCHEMAS_DIR
from pricing_agent.llm import prompts
from pricing_agent.llm.client import LlmResult, complete

BASE_URI = "https://pricing-demo.local/schemas/"

INTENTS = ("SINGLE_VEHICLE", "INVENTORY_PORTFOLIO", "PROMOTION")

# No computed field appears here. That absence is the point.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "vehicle": {
            "type": "object",
            "properties": {
                "vehicle_id": {"type": ["string", "null"]},
                "year": {"type": ["integer", "null"]},
                "make": {"type": ["string", "null"]},
                "model": {"type": ["string", "null"]},
                "trim": {"type": ["string", "null"]},
                "mileage": {"type": ["integer", "null"]},
                "condition": {
                    "type": ["string", "null"],
                    "enum": ["EXCELLENT", "GOOD", "FAIR", "POOR", "UNKNOWN", None],
                },
            },
            "required": ["vehicle_id", "year", "make", "model", "trim", "mileage", "condition"],
            "additionalProperties": False,
        },
        "dealer_context": {
            "type": "object",
            "properties": {
                "acquisition_cost": {"type": ["number", "null"]},
                "reconditioning_cost": {"type": ["number", "null"]},
                "transportation_cost": {"type": ["number", "null"]},
                "current_list_price": {"type": ["number", "null"]},
                "days_in_inventory": {"type": ["integer", "null"]},
            },
            "required": [
                "acquisition_cost",
                "reconditioning_cost",
                "transportation_cost",
                "current_list_price",
                "days_in_inventory",
            ],
            "additionalProperties": False,
        },
        "requested_outputs": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "VALUATION",
                    "PRICING_SCENARIOS",
                    "SALES_FORECAST",
                    "BREAK_EVEN",
                    "PROMOTIONAL_HEADROOM",
                    "DEPRECIATION",
                ],
            },
        },
        "extraction_provenance": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "source": {
                        "type": "string",
                        "enum": ["USER_STATED", "MCP", "CONFIG", "ESTIMATED", "MISSING"],
                    },
                    "note": {"type": ["string", "null"]},
                },
                "required": ["field", "source", "note"],
                "additionalProperties": False,
            },
        },
        "ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["field", "question"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intent", "vehicle", "dealer_context", "requested_outputs",
                 "extraction_provenance", "ambiguities"],
    "additionalProperties": False,
}


def _registry() -> Registry:
    resources = []
    for path in SCHEMAS_DIR.glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((f"{BASE_URI}{path.name}", Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def _validator(name: str) -> Draft202012Validator:
    doc = json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(doc, registry=_registry())


def extract(
    text: str,
    *,
    as_of: datetime,
    dealer_id: str = "DEALER-1001",
    user_id: str = "demo-user",
) -> tuple[dict, LlmResult, list[str]]:
    """Return (request, llm_result, schema_errors).

    A non-empty `schema_errors` means the extraction must not reach a tool.
    """
    result = complete(
        system=prompts.EXTRACTION_SYSTEM,
        user=text,
        recording="extraction_rav4",
        max_tokens=2048,
        output_schema=EXTRACTION_SCHEMA,
    )
    raw = result.content if isinstance(result.content, dict) else {}

    vehicle = {k: v for k, v in (raw.get("vehicle") or {}).items() if v is not None}
    context = {k: v for k, v in (raw.get("dealer_context") or {}).items() if v is not None}

    request = {
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
        "dealer_id": dealer_id,
        "user_id": user_id,
        "as_of": as_of.isoformat(),
        "vehicle": vehicle,
        "dealer_context": context,
        "objective": {"requested_outputs": raw.get("requested_outputs") or []},
        "extraction_provenance": [
            {k: v for k, v in entry.items() if v is not None}
            for entry in (raw.get("extraction_provenance") or [])
        ],
        "ambiguities": raw.get("ambiguities") or [],
    }

    validator = _validator("single-vehicle-request.schema.json")
    errors = [
        f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(request), key=lambda e: list(e.path))
    ]
    return request, result, errors


def intent_of(result: LlmResult) -> str:
    raw = result.content if isinstance(result.content, dict) else {}
    intent = raw.get("intent")
    return intent if intent in INTENTS else "SINGLE_VEHICLE"
