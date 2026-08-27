"""元素反应集成测试共享装配 fixture。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.assembly import build_reaction_assembled


@pytest.fixture
def reaction_assembled(tmp_path: Path):
    def _build(**kwargs):
        return build_reaction_assembled(tmp_path, **kwargs)

    return _build
