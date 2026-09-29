"""月兆伤害修饰 provider：词条阶段、公式自筛与端口读取。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_LUNAR_REACTION,
    DamageModifierIndex,
    DamageModifierStage,
    DamageQuery,
)
from genshin_sim.core.systems.damage.errors import DamageProviderViolationError
from genshin_sim.core.systems.damage.formulas import (
    GeneralDamageFormula,
    validate_formula_modifier_stages,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)
from genshin_sim.core.systems.damage.models import DamageModifierTerm
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierCollection,
    DamageModifierProviderSpec,
    StaticDamageModifierProvider,
)
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.moonsign import (
    MOONSIGN_LUNAR_BONUS_PROVIDER_KEY,
    MoonsignLunarBonusProvider,
    MoonsignValidationError,
)

SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.moonsign_provider")


class _FakeBonusPort:
    """按帧返回固定增伤的只读端口替身。"""

    def __init__(self, values: dict[int, float]) -> None:
        self.values = dict(values)

    def lunar_reaction_bonus(self, frame: int) -> float:
        return self.values.get(frame, 0.0)


class _BadBonusPort:
    """故意违反协议返回非数字，用于验证显式失败。"""

    def lunar_reaction_bonus(self, frame: int) -> float:
        del frame
        return cast("float", "0.2")


class _NullSession:
    """满足 provider 收集协议的最简会话替身。"""

    def begin_provider(self, spec) -> None:
        del spec

    def end_provider(self, spec) -> None:
        del spec


def _query(
    *,
    frame: int = 10,
    formula_key: str = FORMULA_KEY_LUNAR_REACTION,
) -> DamageQuery:
    """provider 只读取帧与公式键，因此用最小查询替身。"""

    return cast(
        "DamageQuery",
        SimpleNamespace(request=SimpleNamespace(frame=frame, formula_key=formula_key)),
    )


def _session() -> DamageResolutionSession:
    """返回满足收集协议的最简会话替身。"""

    return cast("DamageResolutionSession", _NullSession())


def _provider(port: _FakeBonusPort | None = None) -> MoonsignLunarBonusProvider:
    provider = MoonsignLunarBonusProvider()
    if port is not None:
        provider.bind_runtime_ports(bonus_port=port)
    return provider


def test_provider_spec_declares_only_the_lunar_reaction_bonus_stage() -> None:
    """provider 只声明位置 5 的反应加成阶段。"""

    assert MOONSIGN_LUNAR_BONUS_PROVIDER_KEY == "moonsign.lunar_reaction_bonus"
    assert MoonsignLunarBonusProvider.provider_spec.writes == frozenset(
        {DamageModifierStage.LUNAR_REACTION_BONUS_ADD}
    )


def test_unbound_provider_contributes_nothing() -> None:
    """装配期早于端口绑定的查询不受影响。"""

    assert _provider().contribute(_query(), _session()) == ()


def test_zero_bonus_contributes_no_term() -> None:
    """增伤为 0 时不产生词条：槽位基线保持 0，账单不出现空账。"""

    assert _provider(_FakeBonusPort({})).contribute(_query(), _session()) == ()


def test_active_bonus_becomes_one_reaction_bonus_term() -> None:
    """生效增伤产出一个位置 5 词条，值等于小数倍率本身。"""

    terms = _provider(_FakeBonusPort({10: 0.18})).contribute(_query(frame=10), _session())

    assert len(terms) == 1
    term = terms[0]
    assert term.stage is DamageModifierStage.LUNAR_REACTION_BONUS_ADD
    assert term.value == pytest.approx(0.18)
    assert term.provider_key == MOONSIGN_LUNAR_BONUS_PROVIDER_KEY
    assert term.component_key is None
    assert term.audit_tags == ("moonsign.lunar_bonus",)


def test_bonus_is_read_from_the_query_frame() -> None:
    """词条值按查询帧读取，因此覆盖式替换与到期都能被直接观察。"""

    provider = _provider(_FakeBonusPort({10: 0.2}))

    assert provider.contribute(_query(frame=10), _session())[0].value == pytest.approx(0.2)
    assert provider.contribute(_query(frame=11), _session()) == ()


@pytest.mark.parametrize(
    "formula_key",
    [FORMULA_KEY_GENERAL, FORMULA_KEY_TRANSFORMATIVE_REACTION, FORMULA_KEY_STELLAR_REACTION],
    ids=("general", "transformative", "stellar"),
)
def test_non_lunar_formulas_are_filtered_out(formula_key: str) -> None:
    """``lunar_reaction_bonus_add`` 只属于月曜公式；其他公式查询必须完全跳过。"""

    provider = _provider(_FakeBonusPort({10: 0.2}))

    assert provider.contribute(_query(formula_key=formula_key), _session()) == ()


def test_leaked_lunar_stage_on_a_general_query_is_hard_rejected() -> None:
    """反向锚点：不自筛的 provider 会在通用公式上被白名单硬拒绝。

    这正是 provider 必须按公式键自筛的原因——否则整次通用伤害结算会失败。
    """

    leaked = StaticDamageModifierProvider(
        DamageModifierProviderSpec(
            provider_key="test.leaked",
            writes=frozenset({DamageModifierStage.LUNAR_REACTION_BONUS_ADD}),
        ),
        (
            DamageModifierTerm(
                stage=DamageModifierStage.LUNAR_REACTION_BONUS_ADD,
                value=0.2,
                provider_key="test.leaked",
                source_ref=SOURCE_CONTEXT,
            ),
        ),
    )
    collection = DamageModifierIndex((leaked,)).collect(
        _query(formula_key=FORMULA_KEY_GENERAL), _session()
    )

    with pytest.raises(DamageProviderViolationError, match="不允许阶段"):
        validate_formula_modifier_stages(GeneralDamageFormula().formula_spec, collection)


def test_lunar_query_accepts_the_same_collection() -> None:
    """正向对照：同一组词条在月曜公式上通过白名单校验。"""

    index = DamageModifierIndex((_provider(_FakeBonusPort({10: 0.2})),))

    collection = index.collect(_query(), _session())

    assert isinstance(collection, DamageModifierCollection)
    assert len(collection.applied_terms) == 1
    assert collection.rejected_terms == ()


def test_non_numeric_bonus_is_rejected() -> None:
    """端口返回非数字时显式失败，不静默当成 0。"""

    provider = _provider()
    provider.bind_runtime_ports(bonus_port=_BadBonusPort())

    with pytest.raises(MoonsignValidationError, match="非数字"):
        provider.contribute(_query(), _session())
