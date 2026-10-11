"""战狂圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:10005``）；
套装命名采用官方英文名 Berserker（meropide.cn/en/artifacts）。

效果与落点：

- 2 件套：暴击率提高 12% -> ``stat.crit.rate`` ``flat_add``，静态绑定
  穿戴者。
- 4 件套：生命值低于 70% 时，暴击率额外提升 24% -> 通用公式
  ``crit_rate_add`` 阶段，条件经装配期注入的 ``HealthReadAdapter``
  读取穿戴者当前生命比值，静态绑定穿戴者，不落 Buff。

行为约定：

- 4 件套是「瞬时作用于一次伤害」的判定：结算时读当前生命比值，不持有
  状态、不自行计时；生命比值阈值（0.7）来自效果数值的第一段。
- ``crit_rate_add`` 只属于通用公式，必须自筛公式，否则会在反应伤害
  查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
- 生命端口未绑定时（装配完成前）不贡献，条件不会提前生效。
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
    STAT_CRIT_RATE,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

BERSERKER_KEY_PREFIX = "artifact.berserker"
BERSERKER_HANDLER_KEY = BERSERKER_KEY_PREFIX
BERSERKER_2P_HANDLER_KEY = f"{BERSERKER_KEY_PREFIX}.2p"
BERSERKER_4P_HANDLER_KEY = f"{BERSERKER_KEY_PREFIX}.4p"
BERSERKER_CONTENT_VERSION = "release"

BERSERKER_2P_AUDIT_TAG = "berserker_2p"
BERSERKER_4P_AUDIT_TAG = "berserker_4p"


class HealthRatioReadPort(Protocol):
    """内容侧条件效果读取角色当前生命比值的窄只读端口。"""

    def hp_ratio(self, character_ref: AttributeSubjectRef, frame: int) -> float: ...


def create_berserker_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """战狂套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=BERSERKER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BERSERKER_HANDLER_KEY,
        version=BERSERKER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "berserker_set_identity"},
    )


def create_berserker_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """战狂 2 件套：暴击率提高。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=BERSERKER_2P_HANDLER_KEY,
    )
    (crit_rate,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套暴击率加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{BERSERKER_KEY_PREFIX}.2p.crit_rate.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_CRIT_RATE}),
            owner_ref=subject_ref,
            display_name="战狂 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_CRIT_RATE,
                stage=ModifierStage.FLAT_ADD,
                value=crit_rate,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(BERSERKER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BERSERKER_2P_HANDLER_KEY,
        version=BERSERKER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "berserker_2p"},
    )


def create_berserker_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """战狂 4 件套：生命值低于阈值时暴击率额外提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=BERSERKER_4P_HANDLER_KEY,
    )
    hp_threshold, crit_rate = _parse_component_values(
        request.params,
        count=2,
        purpose="4 件套生命阈值/暴击率加成",
    )
    owner_ref = _owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=BERSERKER_4P_HANDLER_KEY,
        version=BERSERKER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            BerserkerLowHpCritProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                hp_threshold=hp_threshold,
                crit_rate=crit_rate,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "berserker_4p"},
    )


class BerserkerLowHpCritProvider:
    """4 件套：装备者生命值低于阈值时，本次伤害暴击率提升。

    条件判定读当前生命比值（当前生命 / 最大生命），阈值取效果数值的
    第一段（0.7）；「低于」按严格小于处理。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        hp_threshold: float,
        crit_rate: float,
    ) -> None:
        if not math.isfinite(hp_threshold) or hp_threshold <= 0 or hp_threshold >= 1:
            raise ContentUnitValidationError("4 件套生命阈值必须是 (0, 1) 内的数")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._hp_threshold = hp_threshold
        self._crit_rate = crit_rate
        self._provider_key = f"{BERSERKER_KEY_PREFIX}.4p.low_hp_crit.slot:{slot}"
        self._source_ref = _source_ref("4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
            owner_ref=self._owner_ref,
            display_name="战狂 4件套·低生命暴击率",
        )
        self._health_port: HealthRatioReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        health_port: HealthRatioReadPort,
    ) -> None:
        """装配期注入生命只读端口；未绑定时不贡献。"""

        self._health_port = health_port

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
        port = self._health_port
        if port is None:
            return ()
        if port.hp_ratio(self._owner_ref, request.frame) >= self._hp_threshold:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=self._crit_rate,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(BERSERKER_4P_AUDIT_TAG,),
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
        f"{BERSERKER_KEY_PREFIX}:{scope}:slot:{slot}",
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
