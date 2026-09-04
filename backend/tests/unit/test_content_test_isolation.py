"""自动化测试与 content/test 开发者内容隔离的门禁。

``content/test`` 只供开发者模式手动/UI 使用，不作为自动化测试依赖；
自动化测试也不得开启 developer_mode 来注入该包，见测试规范。
"""

from __future__ import annotations

from pathlib import Path


def _test_source_files() -> tuple[Path, ...]:
    tests_root = Path(__file__).resolve().parents[1]
    return tuple(sorted(tests_root.rglob("*.py")))


def test_automated_tests_do_not_import_developer_content() -> None:
    forbidden_import = "genshin_sim." + "content.test"
    hits: list[str] = []
    for path in _test_source_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden_import in line:
                hits.append(f"{path}:{line_number}:{line.strip()}")
    assert hits == [], "backend/tests 不得 import content/test：\n" + "\n".join(hits)


def test_automated_tests_do_not_enable_developer_mode() -> None:
    forbidden_mode = "developer_mode=" + "True"
    hits: list[str] = []
    for path in _test_source_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden_mode in line:
                hits.append(f"{path}:{line_number}:{line.strip()}")
    assert hits == [], "backend/tests 不得开启 developer_mode：\n" + "\n".join(hits)
