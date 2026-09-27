"""桑多涅效果单元工厂的分量读取与效果行名称契约。

C4 的效果行分量按位置读取，位置顺序即为契约：星超导倍率 / 星扩散倍率 /
冷却秒数（官方文本的 125%/187.5% 依次排列，冷却秒数为末位纯数分量）。
资产源增删分量会平移这些位置，因此这里锁住顺序，避免再次静默读到相邻分量。

C4 hook 的星烁擢升来自 C6 的效果行（跨效果行的机器耦合），由拥有者上下文
``effect_params`` 传入，这里锁定「解锁第 6 层才有、且取自 C6 行」。

效果行的正式名称（``params.name``）同样来自资产：错误定位与审计显示名都用它，
这里锁定「有名称则取自效果行、无名称则报错」。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.effects import (
    create_sandrone_constellation_c1,
    create_sandrone_constellation_c2,
    create_sandrone_constellation_c3,
    create_sandrone_constellation_c4,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    SandroneC1StellarBonusProvider,
    SandroneC2RayCritDamageProvider,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.registries import EffectContentUnitRequest, EffectOwnerContext
from tests.helpers import sandrone as sandrone_helpers

C1_EFFECT_KEY = f"{SANDRONE_ASSET_KEY}:constellation:c1"
C2_EFFECT_KEY = f"{SANDRONE_ASSET_KEY}:constellation:c2"
C3_EFFECT_KEY = f"{SANDRONE_ASSET_KEY}:constellation:c3"
C4_EFFECT_KEY = f"{SANDRONE_ASSET_KEY}:constellation:c4"


def _components(*specs: tuple[float, str], name: str | None = "合成命座4") -> dict[str, object]:
    params: dict[str, object] = {
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
    if name is not None:
        params["name"] = name
    return params


def _constellation_request(
    *,
    handler_key: str,
    effect_key: str,
    unlock_key: str,
    params: dict[str, object],
    constellation: int,
    effect_params: dict[str, dict[str, object]] | None = None,
) -> EffectContentUnitRequest:
    return EffectContentUnitRequest(
        handler_key=handler_key,
        effect_key=effect_key,
        effect_kind="constellation",
        owner_type="character",
        owner_key=SANDRONE_ASSET_KEY,
        slot=1,
        params=params,
        unlock_key=unlock_key,
        owner_context=EffectOwnerContext(
            constellation=constellation,
            effect_params=(
                sandrone_helpers.character_effect_params()
                if effect_params is None
                else effect_params
            ),
        ),
    )


def _c4_request(
    params: dict[str, object],
    *,
    constellation: int = 4,
    effect_params: dict[str, dict[str, object]] | None = None,
):
    return _constellation_request(
        handler_key=SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
        effect_key=C4_EFFECT_KEY,
        unlock_key="c4",
        params=params,
        constellation=constellation,
        effect_params=effect_params,
    )


def _c4_hook(
    params: dict[str, object],
    *,
    constellation: int = 4,
    effect_params: dict[str, dict[str, object]] | None = None,
) -> SandroneC4CoordinatedAttackHook:
    unit = create_sandrone_constellation_c4(
        _c4_request(
            params,
            constellation=constellation,
            effect_params=effect_params,
        )
    )
    hook = unit.event_hooks[0]
    assert isinstance(hook, SandroneC4CoordinatedAttackHook)
    return hook


def test_c1_display_name_comes_from_the_effect_row():
    unit = create_sandrone_constellation_c1(
        _constellation_request(
            handler_key=SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
            effect_key=C1_EFFECT_KEY,
            unlock_key="c1",
            params=_components(
                (11330001.0, "number"),
                (11330002.0, "number"),
                (0.5, "percent"),
                (0.3, "percent"),
                name="合成命座1",
            ),
            constellation=1,
        )
    )
    provider = unit.damage_modifier_providers[0]
    assert isinstance(provider, SandroneC1StellarBonusProvider)
    assert provider.provider_spec.display_name == "合成命座1·星烁增伤"


def test_c2_display_name_comes_from_the_effect_row():
    unit = create_sandrone_constellation_c2(
        _constellation_request(
            handler_key=SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
            effect_key=C2_EFFECT_KEY,
            unlock_key="c2",
            params=_components(
                (0.4, "percent"),
                (11330001.0, "number"),
                (0.2, "percent"),
                (3.0, "number"),
                name="合成命座2",
            ),
            constellation=2,
        )
    )
    provider = unit.damage_modifier_providers[0]
    assert isinstance(provider, SandroneC2RayCritDamageProvider)
    assert provider.provider_spec.display_name == "合成命座2·射线暴伤"


def test_constellation_row_without_name_is_rejected():
    with pytest.raises(ContentUnitValidationError, match="资产效果行缺少名称"):
        create_sandrone_constellation_c3(
            _constellation_request(
                handler_key=SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
                effect_key=C3_EFFECT_KEY,
                unlock_key="c3",
                params=_components(
                    (11331.0, "number"), (3.0, "number"), (15.0, "number"), name=None
                ),
                constellation=3,
            )
        )


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


def test_c4_ascension_bonus_comes_from_the_c6_effect_row():
    row = _components((1.25, "percent"), (1.875, "percent"), (4.0, "number"))
    # 0–5 命：没有 C6，协同攻击不带擢升。
    assert _c4_hook(row, constellation=5).ascension_bonus == pytest.approx(0.0)
    # 6 命：擢升取自 C6 效果行的末位分量（合成行 20%）。
    assert _c4_hook(row, constellation=6).ascension_bonus == pytest.approx(0.2)


def test_c4_ascension_requires_the_c6_row_once_unlocked():
    with pytest.raises(ContentUnitValidationError, match="C6 资产效果行"):
        _c4_hook(
            _components((1.25, "percent"), (1.875, "percent"), (4.0, "number")),
            constellation=6,
            effect_params={},
        )
