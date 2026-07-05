from __future__ import annotations

import pytest

from genshin_sim.content import (
    NOOP_HANDLER_KEY,
    HandlerNotFoundError,
    HandlerRegistry,
    RuntimeHandlerRequest,
    create_default_registry,
)


def test_default_registry_exposes_noop_handler():
    registry = create_default_registry()

    assert NOOP_HANDLER_KEY in registry


def test_registry_rejects_duplicate_handler_key():
    registry = HandlerRegistry()
    registry.register_factory("generic.test", lambda request: request)

    with pytest.raises(ValueError, match="duplicate handler_key"):
        registry.register_factory("generic.test", lambda request: request)


def test_registry_returns_handler_result():
    registry = HandlerRegistry()
    registry.register_factory("generic.test", lambda request: request.owner_key)
    request = RuntimeHandlerRequest(
        handler_key="generic.test",
        owner_type="character",
        owner_key="character:75",
    )

    assert registry.create(request) == "character:75"


def test_registry_raises_when_missing_handler():
    registry = HandlerRegistry()

    with pytest.raises(HandlerNotFoundError, match="missing handler: missing"):
        registry.create(
            RuntimeHandlerRequest(
                handler_key="missing",
                owner_type="character",
                owner_key="character:75",
            )
        )
