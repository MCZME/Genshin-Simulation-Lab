"""月曜反应系数与分配权重的 golden 基线。

验证能力：反应月感电 / 反应月结晶的复合伤害口径。机制侧传入的反应系数是「未折入」
写法（月感电 3.0、月结晶 1.6），分配权重是 ``0.60 : 0.30 : 0.05``；两者相乘后
最高组分的实际系数等于资料折入口径的「反应倍率 1.8 / 0.96 配 1 : 1/2 : 1/12 分配」。
本文件钉住这条等价关系，防止只改权重或只改系数造成 0.60 被重复计入。

资料来源及适用版本：米游社《元素反应(高等元素论)》(article/25901063)：
「直伤月反应倍率(月感电 3.0, 月结晶倍率 1.6)，反应月反应倍率(月感电 1.8, 月结晶 0.96)」；
米游社《月曜反应》(article/77019346)：分配系数「0.6 × 第一高 + 0.3 × 第二高 +
0.05 × 其他」；BWIKI《元素反应》页「反应倍率」表与《月结晶伤害公式》页。
覆盖月之八版本。

完整输入条件：90 级参与者、0 元素精通、目标 0 雷抗、必不暴击、无擢升、无附加伤害、
无反应加成词条；等级基数取生产表 ``PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE[90]``。

预期输出与允许误差：精确小数断言（相对 1e-12）。

不覆盖的行为：月感电 / 月结晶的触发条件、雷暴云与月笼的状态机、组分暴击排序与
抗性 / 擢升区的具体数值（另见 `tests/unit` 与 reactions 目录下的 golden）。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_LUNAR_REACTION,
    DamageQuery,
    DamageRequest,
    DamageResolver,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.enums import LunarReactionDamageMode
from genshin_sim.core.systems.damage.formulas import (
    PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE,
)
from genshin_sim.core.systems.damage.lunar import LUNAR_COMPOSITE_WEIGHTS
from genshin_sim.core.systems.damage.models import (
    LunarReactionDamageInput,
    LunarReactionParticipantInput,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER,
)
from tests.helpers import damage

TARGET = AttributeSubjectRef.target("target:lunar_golden")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "golden.lunar_coefficient")
PARTICIPANTS = tuple(
    AttributeSubjectRef.character(f"character:slot_{slot}") for slot in range(1, 5)
)
LEVEL_BASE_90 = PRODUCTION_LUNAR_REACTION_LEVEL_BASE_DAMAGE[90]


def _attribute_resolver() -> AttributeResolver:
    """0 元素精通参与者与 0 雷抗目标的最小属性环境。"""

    return damage.make_attribute_resolver(
        PARTICIPANTS,
        target=TARGET,
        source_context=SOURCE_CONTEXT,
    )


def _composite_damage(*, reaction_multiplier: float, participant_count: int) -> float:
    """按生产默认公式结算一次反应复合月曜伤害，返回官方伤害值。"""

    participants = tuple(
        LunarReactionParticipantInput(
            participant_ref=PARTICIPANTS[index],
            source_level=90,
            can_crit=False,
        )
        for index in range(participant_count)
    )
    request = DamageRequest(
        request_id="request:lunar-golden",
        frame=0,
        formula_key=FORMULA_KEY_LUNAR_REACTION,
        main_attack_tag="月曜 golden",
        impact_key="impact:lunar-golden",
        source_ref=PARTICIPANTS[0],
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=SOURCE_CONTEXT,
        scaling_terms=(),
        lunar_reaction=LunarReactionDamageInput(
            reaction_profile_key="reaction_profile.lunar.golden",
            mode=LunarReactionDamageMode.REACTION_COMPOSITE,
            participants=participants,
            reaction_multiplier=reaction_multiplier,
        ),
    )
    tags = request.tags
    result = DamageResolver(
        attribute_resolver=_attribute_resolver(),
        formula_registry=create_default_damage_formula_registry(),
    ).resolve(
        DamageQuery(
            request=request,
            source_attribute_context=AttributeQueryContext(tags=tags, target_ref=TARGET),
            target_attribute_context=AttributeQueryContext(
                tags=tags,
                source_ref=SOURCE_CONTEXT,
                target_ref=PARTICIPANTS[0],
            ),
        )
    )
    return float(result.official_damage)


@pytest.mark.parametrize(
    ("coefficient", "folded"),
    [
        (LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER, 1.8),
        (LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER, 0.96),
    ],
    ids=("electro_charged", "crystallize"),
)
def test_reaction_coefficient_and_weights_are_one_folded_pair(coefficient, folded) -> None:
    """未折入系数 × 最高权重 == 资料折入口径的反应倍率。"""

    assert LUNAR_COMPOSITE_WEIGHTS[0] == pytest.approx(0.60, rel=0.0, abs=1e-12)
    assert coefficient * LUNAR_COMPOSITE_WEIGHTS[0] == pytest.approx(folded, rel=1e-12)


def test_composite_weights_match_the_reference_distribution() -> None:
    """``0.60 : 0.30 : 0.05`` 与资料 ``1 : 1/2 : 1/12`` 是同一组比例。"""

    assert LUNAR_COMPOSITE_WEIGHTS == (0.60, 0.30, 0.05)
    assert LUNAR_COMPOSITE_WEIGHTS[1] / LUNAR_COMPOSITE_WEIGHTS[0] == pytest.approx(
        1 / 2, rel=1e-12
    )
    assert LUNAR_COMPOSITE_WEIGHTS[2] / LUNAR_COMPOSITE_WEIGHTS[0] == pytest.approx(
        1 / 12, rel=1e-12
    )


@pytest.mark.parametrize(
    ("reaction_multiplier", "unfolded_coefficient", "folded_multiplier"),
    [
        (LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER, 3.0, 1.8),
        (LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER, 1.6, 0.96),
    ],
    ids=("electro_charged", "crystallize"),
)
def test_single_participant_equals_level_base_times_folded_multiplier(
    reaction_multiplier: float,
    unfolded_coefficient: float,
    folded_multiplier: float,
) -> None:
    """单参与者反应月曜：等级基数 × 未折入系数 × 0.60 == 等级基数 × 资料折入倍率。"""

    official_damage = _composite_damage(
        reaction_multiplier=reaction_multiplier,
        participant_count=1,
    )

    assert official_damage == pytest.approx(LEVEL_BASE_90 * unfolded_coefficient * 0.60, rel=1e-12)
    assert official_damage == pytest.approx(LEVEL_BASE_90 * folded_multiplier, rel=1e-12)


def test_lunar_electro_charged_four_participants_total_weight_is_one() -> None:
    """四名等值参与者：权重合计 1.0，等价于折入口径的 ``1 + 1/2 + 1/12 + 1/12``。"""

    damage = _composite_damage(
        reaction_multiplier=LUNAR_ELECTRO_CHARGED_REACTION_MULTIPLIER,
        participant_count=4,
    )
    folded_distribution = 1 + 1 / 2 + 1 / 12 + 1 / 12

    assert sum(LUNAR_COMPOSITE_WEIGHTS) + LUNAR_COMPOSITE_WEIGHTS[-1] == pytest.approx(1.0)
    assert damage == pytest.approx(LEVEL_BASE_90 * 3.0 * 1.0, rel=1e-12)
    assert damage == pytest.approx(LEVEL_BASE_90 * 1.8 * folded_distribution, rel=1e-12)
