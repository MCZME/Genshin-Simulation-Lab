"""内置内容实现和 handler 注册。"""

from genshin_sim.content.bootstrap import (
    BUILTIN_NOOP_HANDLER_KEYS,
    create_default_registry,
    register_builtin_content,
)
from genshin_sim.content.registry import (
    NOOP_HANDLER_KEY,
    DuplicateHandlerError,
    HandlerFactory,
    HandlerNotFoundError,
    HandlerRegistry,
    NoOpRuntimeHandler,
    RegistryError,
    RuntimeHandler,
    RuntimeHandlerRequest,
)

__all__ = [
    "NOOP_HANDLER_KEY",
    "BUILTIN_NOOP_HANDLER_KEYS",
    "DuplicateHandlerError",
    "HandlerFactory",
    "HandlerNotFoundError",
    "HandlerRegistry",
    "NoOpRuntimeHandler",
    "RegistryError",
    "RuntimeHandler",
    "RuntimeHandlerRequest",
    "create_default_registry",
    "register_builtin_content",
]
