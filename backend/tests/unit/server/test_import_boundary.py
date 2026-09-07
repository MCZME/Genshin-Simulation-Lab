"""server 入口模块导入边界测试。"""

import ast
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[3] / "src" / "genshin_sim" / "server"


def _is_allowed_module(module: str) -> bool:
    if module == "genshin_sim.application" or module.startswith("genshin_sim.server"):
        return True
    return not module.startswith("genshin_sim")


def test_server_only_imports_application_public_surface() -> None:
    for path in sorted(SERVER_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert _is_allowed_module(alias.name), f"{path}: forbidden import {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert _is_allowed_module(node.module), f"{path}: forbidden import {node.module}"
