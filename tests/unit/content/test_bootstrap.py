from __future__ import annotations

import pytest

from genshin_sim.content import (
    BUILTIN_NOOP_HANDLER_KEYS,
    NOOP_HANDLER_KEY,
    DuplicateHandlerError,
    HandlerRegistry,
    RuntimeHandlerRequest,
    create_default_registry,
    register_builtin_content,
)


def test_register_builtin_content_registers_noop_handler_explicitly():
    registry = HandlerRegistry()

    assert not registry.has_handler(NOOP_HANDLER_KEY)

    returned = register_builtin_content(registry)

    assert returned is registry
    assert registry.handler_keys == tuple(sorted(BUILTIN_NOOP_HANDLER_KEYS))


def test_default_registry_can_run_noop_handler():
    registry = create_default_registry()
    request = RuntimeHandlerRequest(
        handler_key=NOOP_HANDLER_KEY,
        owner_type="test",
        owner_key="test:noop",
        params={"reason": "placeholder"},
    )

    handler = registry.create(NOOP_HANDLER_KEY)
    result = handler.prepare_runtime(request)

    assert result is None


def test_builtin_bootstrap_does_not_silently_replace_existing_handler():
    registry = create_default_registry()

    with pytest.raises(DuplicateHandlerError, match=NOOP_HANDLER_KEY):
        register_builtin_content(registry)
