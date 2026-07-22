"""Shared fixtures. Scenario definitions in tests/scenarios/*.json drive the integration
tests, so a scenario and its test cannot drift apart."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
SCENARIO_DIR = ROOT / "tests" / "scenarios"
BASE_URI = "https://pricing-demo.local/schemas/"

DEFAULT_AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def schema_registry() -> Registry:
    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((f"{BASE_URI}{path.name}", Resource.from_contents(doc)))
    return Registry().with_resources(resources)


@pytest.fixture(scope="session")
def validator_for(schema_registry):
    def _make(schema_name: str) -> Draft202012Validator:
        doc = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
        return Draft202012Validator(doc, registry=schema_registry)

    return _make


@pytest.fixture(scope="session")
def scenarios():
    def _load(suite: str) -> dict:
        doc = json.loads((SCENARIO_DIR / f"{suite}.json").read_text(encoding="utf-8"))
        return {s["id"]: s for s in doc["scenarios"]}

    return _load


@pytest.fixture
def as_of() -> datetime:
    return DEFAULT_AS_OF


@pytest.fixture
def config():
    from pricing_agent.config import load_config

    return load_config()


@pytest.fixture
def transport(as_of):
    """A fresh transport per test, so mutations never leak between scenarios."""
    from pricing_agent.mcp_clients import FixtureStore, MockTransport

    return MockTransport(as_of=as_of, store=FixtureStore())


def make_transport(as_of: datetime, mutations=()):
    from pricing_agent.mcp_clients import FixtureStore, Mutation, MockTransport

    parsed = [m if isinstance(m, Mutation) else Mutation(**m) for m in mutations]
    return MockTransport(as_of=as_of, store=FixtureStore(mutations=parsed))
