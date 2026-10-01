"""桑多涅 C2 射线暴伤换算与请求级事实作用域的 golden 基线。

验证能力：伤害请求级事实（D-085）作为 provider 判定输入的换算口径。射线
会话序号在发射时刻绑定于 ``DamageRequest.request_facts``，C2 provider 读取后
换算为暴伤加成词条 ``暴伤加成 = 0.4 + 0.2 × min(序号, 3)``（含当发射线，
至多计入 3 条）；同一请求的全部目标结算读到同一份事实（这是请求级事实与
「结算时计数」方案的本质差异——逐目标结算不改变取值）。

资料来源及适用版本：桑多涅（character:10000133）命座第 2 层效果行
「+40% 基础、逐射线 +20%、至多 3 层」，源数据
``backend/data/assets/sources/project_amber_yatta/default_full/avatar/10000133.json``，
经资产库效果行接入（data.py SANDRONE_C2_*；helper 资产库以合成数值复刻同一
口径）。覆盖资料接入当期的资产库快照。

完整输入条件：90 级来源、目标 0 冰抗、暴击词条只含 C2 换算项；射线请求携带
星超导冰主标签与星超导附加标签，请求级事实 ``sandrone.fageou.ray_index`` 分别
绑定 1/2/3/4。

预期输出与允许误差：精确小数断言（相对 1e-12）。

不覆盖的行为：射线发射节奏与会话序号推进（法洁欧状态机，见 tests/integration
content/sandrone）、非星超导标签与外来来源的过滤（tests/unit content 用例）、
会话级容器转发（tests/unit/core facts 用例）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_INDEX_FACT_KEY,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    SandroneC2RayCritDamageProvider,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    DamageModifierIndex,
    DamageQuery,
    DamageRequest,
    DamageResolutionScope,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.enums import DamageModifierStage
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL

SOURCE = AttributeSubjectRef.character("character:slot_1")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "golden.sandrone_c2_fact")

# 资产效果行数值（桑多涅命座第 2 层）：+40% 基础、逐射线 +20%、至多 3 层。
C2_CRIT_DAMAGE_BASE = 0.4
C2_CRIT_DAMAGE_PER_RAY = 0.2
C2_CRIT_DAMAGE_MAX_RAYS = 3

PROVIDER_SOURCE_KEY = "character.sandrone.constellation.c2"


def _resolver_with_c2() -> tuple[DamageModifierIndex, AttributeResolver]:
    provider = SandroneC2RayCritDamageProvider(
        owner_ref=SOURCE.entity_id,
        crit_damage_base=C2_CRIT_DAMAGE_BASE,
        crit_damage_per_ray=C2_CRIT_DAMAGE_PER_RAY,
        max_rays=C2_CRIT_DAMAGE_MAX_RAYS,
        source_key=PROVIDER_SOURCE_KEY,
        display_name="回望镜中，时岁翩然·射线暴伤",
    )
    registry = create_public_attribute_registry()
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )
    return DamageModifierIndex((provider,)), attribute_resolver


def _ray_query(ray_index: int, *, target: AttributeSubjectRef) -> DamageQuery:
    request = DamageRequest(
        request_id=f"damage:golden:c2:ray:{ray_index}:{target.entity_id}",
        frame=400,
        formula_key=FORMULA_KEY_GENERAL,
        main_attack_tag="星超导冰",
        impact_key="character.sandrone.charged.ray",
        source_ref=SOURCE,
        target_ref=target,
        source_level=90,
        target_level=90,
        element=Element.CRYO,
        scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
        tags=frozenset({SANDRONE_RAY_STELLAR_ADDITIONAL_TAG}),
        request_facts={FAGEOU_RAY_INDEX_FACT_KEY: ray_index},
        can_crit=False,
        source_context=SOURCE_CONTEXT,
    )
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(target_ref=target),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )


def _c2_bonus(query: DamageQuery, modifier_index, attribute_resolver) -> float:
    scope = DamageResolutionScope(attribute_resolver, query)
    collection = modifier_index.collect(query, scope)
    c2_terms = [
        term
        for term in collection.applied_terms
        if term.stage is DamageModifierStage.CRIT_DAMAGE_ADD
    ]
    assert len(c2_terms) == 1
    return float(c2_terms[0].value)


@pytest.mark.parametrize(
    ("ray_index", "expected_bonus"),
    [
        (1, C2_CRIT_DAMAGE_BASE + C2_CRIT_DAMAGE_PER_RAY),
        (2, C2_CRIT_DAMAGE_BASE + 2 * C2_CRIT_DAMAGE_PER_RAY),
        (3, C2_CRIT_DAMAGE_BASE + 3 * C2_CRIT_DAMAGE_PER_RAY),
        (4, C2_CRIT_DAMAGE_BASE + 3 * C2_CRIT_DAMAGE_PER_RAY),
    ],
)
def test_c2_ray_crit_damage_conversion_from_request_fact(ray_index: int, expected_bonus: float):
    """序号 1..4 的换算：+0.2 逐射线、第 4 发起与第 3 发持平（至多 3 层）。"""

    modifier_index, attribute_resolver = _resolver_with_c2()
    bonus = _c2_bonus(
        _ray_query(ray_index, target=AttributeSubjectRef.target("target:c2_golden")),
        modifier_index,
        attribute_resolver,
    )

    assert bonus == pytest.approx(expected_bonus, rel=1e-12)


def test_request_fact_is_identical_across_all_targets_of_one_request():
    """同一射线请求的多个目标各自结算，读到同一份请求级事实（不因逐目标而漂移）。"""

    modifier_index, attribute_resolver = _resolver_with_c2()
    targets = (
        AttributeSubjectRef.target("target:c2_a"),
        AttributeSubjectRef.target("target:c2_b"),
        AttributeSubjectRef.target("target:c2_c"),
    )

    bonuses = [
        _c2_bonus(_ray_query(2, target=target), modifier_index, attribute_resolver)
        for target in targets
    ]

    assert bonuses[0] == bonuses[1] == bonuses[2] == pytest.approx(0.8, rel=1e-12)
