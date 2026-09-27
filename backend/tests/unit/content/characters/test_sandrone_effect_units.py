"""桑多涅效果单元工厂的分量读取契约。

C4 的效果行分量按位置读取，位置顺序即为契约：星超导倍率 / 星扩散倍率 /
冷却秒数（官方文本的 125%/187.5% 依次排列，冷却秒数为末位纯数分量）。
资产源增删分量会平移这些位置，因此这里锁住顺序，避免再次静默读到相邻分量。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.effects import (
    create_sandrone_constellation_c4,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.registries import EffectContentUnitRequest, EffectOwnerContext

C4_EFFECT_KEY = f"{SANDRONE_ASSET_KEY}:constellation:c4"


def _components(*specs: tuple[float, str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "components": [
            {
                "source_param": f"number_{index}",
                "kind": "numeric",
                "format": component_format,
                "values": [value],
            }
            for index, (value, component_format) in enumerate(specs, start=1)
        ],
    }


def _c4_request(params: dict[str, object], *, constellation: int = 4):
    return EffectContentUnitRequest(
        handler_key=SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
        effect_key=C4_EFFECT_KEY,
        effect_kind="constellation",
        owner_type="character",
        owner_key=SANDRONE_ASSET_KEY,
        slot=1,
        params=params,
        unlock_key="c4",
        owner_context=EffectOwnerContext(constellation=constellation),
    )


def _c4_hook(params: dict[str, object]) -> SandroneC4CoordinatedAttackHook:
    unit = create_sandrone_constellation_c4(_c4_request(params))
    hook = unit.event_hooks[0]
    assert isinstance(hook, SandroneC4CoordinatedAttackHook)
    return hook


def test_c4_reads_ratios_and_cooldown_in_row_order():
    hook = _c4_hook(_components((1.25, "percent"), (1.875, "percent"), (4.0, "number")))

    assert hook.attack_ratio == pytest.approx(1.25)
    assert hook.swirl_ratio == pytest.approx(1.875)
    assert hook.cooldown_frames == 240


def test_c4_rejects_row_shape_without_cooldown_component():
    with pytest.raises(ContentUnitValidationError):
        _c4_hook(_components((1.25, "percent"), (1.875, "percent")))


def test_c4_rejects_non_positive_ratio():
    with pytest.raises(ContentUnitValidationError):
        _c4_hook(_components((1.25, "percent"), (0.0, "percent"), (4.0, "number")))
