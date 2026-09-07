"""CLI 入口模块导入边界测试。"""

import ast
import sys
from pathlib import Path

CLI_MAIN = Path(__file__).resolve().parents[3] / "src" / "genshin_sim" / "cli" / "main.py"

_ALLOWED_PREFIXES = (
    "genshin_sim.application",
    "genshin_sim.cli",
    "genshin_sim.infrastructure.logging",
)


def _is_allowed_module(module: str) -> bool:
    if module == "__future__" or module.split(".", 1)[0] in sys.stdlib_module_names:
        return True
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in _ALLOWED_PREFIXES)


def test_cli_does_not_import_internal_business_modules() -> None:
    tree = ast.parse(CLI_MAIN.read_text(encoding="utf-8"), filename=str(CLI_MAIN))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert _is_allowed_module(alias.name), f"forbidden import {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            assert _is_allowed_module(node.module), f"forbidden import {node.module}"
