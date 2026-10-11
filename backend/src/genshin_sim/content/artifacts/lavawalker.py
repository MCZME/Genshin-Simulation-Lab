"""渡过烈火的贤人圣遗物套装实现。

效果与落点：

- 2 件套：火元素抗性提高 40% -> ``resistance.pyro`` ``flat_add``，
  静态绑定穿戴者。
- 4 件套：对处于火元素影响下的敌人造成的伤害提升 35% -> 通用公式
  ``damage_bonus_add`` 阶段，条件经装配期注入的
  ``TargetElementAuraReadAdapter`` 查目标是否带有火元素附着分量，
  静态绑定穿戴者，不落 Buff。

行为约定：

- 「处于火元素影响下」按 Aura 分量判定：目标带有 ``pyro`` 或
  ``burning`` 分量即视为受火元素影响。燃烧状态在 Aura 系统中是独立
  分量（且不保证与 ``pyro`` 分量并存），而燃烧中的敌人按游戏行为属于
  「受火元素影响」，故同时检查两种分量。
- 伤害 provider 自筛公式：``damage_bonus_add`` 只属于通用公式，越界
  阶段会被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
- 附着端口未绑定时（装配完成前）不贡献，条件不会提前生效。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Protocol

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    RESISTANCE_PYRO,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.elements import AuraKind
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

LAVAWALKER_KEY_PREFIX = "artifact.lavawalker"
LAVAWALKER_HANDLER_KEY = LAVAWALKER_KEY_PREFIX
LAVAWALKER_2P_HANDLER_KEY = f"{LAVAWALKER_KEY_PREFIX}.2p"
LAVAWALKER_4P_HANDLER_KEY = f"{LAVAWALKER_KEY_PREFIX}.4p"
LAVAWALKER_CONTENT_VERSION = "release"

LAVAWALKER_2P_AUDIT_TAG = "lavawalker_2p"
LAVAWALKER_4P_AUDIT_TAG = "lavawalker_4p"

LAVAWALKER_AFFECTED_AURA_KINDS = (AuraKind.PYRO, AuraKind.BURNING)


class TargetElementAuraReadPort(Protocol):
    """内容侧条件效果读取目标元素附着状态的窄只读端口。"""

    def has_component(
        self,
        target_ref: AttributeSubjectRef,
        aura_kind: AuraKind,
        frame: int,
    ) -> bool: ...


def create_lavawalker_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """渡过烈火的贤人套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=LAVAWALKER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=LAVAWALKER_HANDLER_KEY,
        version=LAVAWALKER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "lavawalker_set_identity"},
    )


def create_lavawalker_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """渡过烈火的贤人 2 件套：火元素抗性提高。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=LAVAWALKER_2P_HANDLER_KEY,
    )
    (resistance,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套火元素抗性加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{LAVAWALKER_KEY_PREFIX}.2p.pyro_res.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({RESISTANCE_PYRO}),
            owner_ref=subject_ref,
            display_name="渡过烈火的贤人 2件套",
        ),
        (
            ModifierTerm(
                target_key=RESISTANCE_PYRO,
                stage=ModifierStage.FLAT_ADD,
                value=resistance,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(LAVAWALKER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=LAVAWALKER_2P_HANDLER_KEY,
        version=LAVAWALKER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "lavawalker_2p"},
    )


def create_lavawalker_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """渡过烈火的贤人 4 件套：对受火元素影响的敌人伤害提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=LAVAWALKER_4P_HANDLER_KEY,
    )
    (damage_bonus,) = _parse_component_values(
        request.params,
        count=1,
        purpose="4 件套对火影响敌人伤害加成",
    )
    owner_ref = _owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=LAVAWALKER_4P_HANDLER_KEY,
        version=LAVAWALKER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            LavawalkerPyroAffectedBonusProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                bonus=damage_bonus,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "lavawalker_4p"},
    )


class LavawalkerPyroAffectedBonusProvider:
    """4 件套：对处于火元素影响下的敌人造成的伤害提升。

    ``damage_bonus_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(self, *, owner_ref: str, slot: int, bonus: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus = bonus
        self._provider_key = f"{LAVAWALKER_KEY_PREFIX}.4p.pyro_bonus.slot:{slot}"
        self._source_ref = _source_ref("4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="渡过烈火的贤人 4件套",
        )
        self._aura_port: TargetElementAuraReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        element_aura_port: TargetElementAuraReadPort,
    ) -> None:
        """装配期注入目标附着只读端口；未绑定时不贡献。"""

        self._aura_port = element_aura_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.formula_key is not FORMULA_KEY_GENERAL:
            return ()
        if request.target_ref.kind is not AttributeSubjectKind.TARGET:
            return ()
        port = self._aura_port
        if port is None:
            return ()
        if not any(
            port.has_component(request.target_ref, aura_kind, request.frame)
            for aura_kind in LAVAWALKER_AFFECTED_AURA_KINDS
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(LAVAWALKER_4P_AUDIT_TAG,),
            ),
        )


def _require_piece_count(
    request: ArtifactContentUnitRequest,
    *,
    expected: int,
    handler_key: str,
) -> None:
    """件数效果键必须绑定到对应件数的效果行。"""

    if request.piece_count != expected:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定 {expected} 件套效果，收到 {request.piece_count} 件"
        )


def _require_set_row(request: ArtifactContentUnitRequest, *, handler_key: str) -> None:
    """套装索引行单元键只能绑定套装索引行，不能绑定件数效果行。"""

    if request.piece_count is not None:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定套装索引行，收到 {request.piece_count} 件套效果行"
        )


def _owner_ref(slot: int) -> str:
    return f"character:slot_{slot}"


def _source_ref(scope: str, slot: int) -> RuntimeSourceRef:
    return RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{LAVAWALKER_KEY_PREFIX}:{scope}:slot:{slot}",
    )


def _parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取数值列表（与正式内容 components 约定一致）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
