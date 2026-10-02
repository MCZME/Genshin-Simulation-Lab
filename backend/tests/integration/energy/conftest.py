"""元素能量系统集成测试共享装配 fixture。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.assembly import build_fixture_assembled


@pytest.fixture
def energy_assembled(tmp_path: Path):
    """零行为夹具角色的装配仿真；默认双手剑以获得 0% 初始回能概率。"""

    def _build(**kwargs):
        kwargs.setdefault("character_weapon_type", "claymore")
        return build_fixture_assembled(tmp_path, **kwargs)

    return _build
