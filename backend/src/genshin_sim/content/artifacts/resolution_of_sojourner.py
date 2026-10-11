"""行者之心圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:10001``）；
套装命名采用官方英文名 Resolution of Sojourner（meropide.cn/en/artifacts）。

效果与落点：

- 2 件套：攻击力提高 18% -> ``stat.atk.total`` 的 ``percent_add``，
  静态绑定穿戴者。
- 4 件套：重击的暴击率提升 30% -> 通用公式 ``crit_rate_add`` 阶段，
  按 ``main_attack_tag == "重击"`` 过滤，静态绑定穿戴者，不落 Buff。

行为约定：

- 4 件套是「瞬时作用于一次伤害」的判定，与影中沉凝的幻灭 C3 同型：
  ``crit_rate_add`` 的契约语义就是「只参与本次伤害的暴击率调整」，写进
  面板或做成有生命周期的 Buff 都会把作用域放大到多次伤害。
- 「重击」按内容层攻击标签约定识别：各角色重击伤害统一使用
  ``"重击"`` 主攻击标签。
- 伤害 provider 自筛公式：``crit_rate_add`` 只属于通用公式，越界阶段
  会被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
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

RESOLUTION_OF_SOJOURNER_KEY_PREFIX = "artifact.resolution_of_sojourner"
RESOLUTION_OF_SOJOURNER_HANDLER_KEY = RESOLUTION_OF_SOJOURNER_KEY_PREFIX
RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.2p"
RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.4p"
RESOLUTION_OF_SOJOURNER_CONTENT_VERSION = "release"

RESOLUTION_OF_SOJOURNER_2P_AUDIT_TAG = "resolution_of_sojourner_2p"
RESOLUTION_OF_SOJOURNER_4P_AUDIT_TAG = "resolution_of_sojourner_4p"

CHARGED_ATTACK_MAIN_ATTACK_TAG = "重击"


def create_resolution_of_sojourner_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=RESOLUTION_OF_SOJOURNER_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "resolution_of_sojourner_set_identity"},
    )


def create_resolution_of_sojourner_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心 2 件套：攻击力提高。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
    )
    (atk_percent,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套攻击力加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.2p.atk_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ATK_TOTAL}),
            owner_ref=subject_ref,
            display_name="行者之心 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=atk_percent,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(RESOLUTION_OF_SOJOURNER_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_2P_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "resolution_of_sojourner_2p"},
    )


def create_resolution_of_sojourner_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """行者之心 4 件套：重击的暴击率提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
    )
    (crit_rate,) = _parse_component_values(
        request.params,
        count=1,
        purpose="4 件套重击暴击率加成",
    )
    owner_ref = _owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=RESOLUTION_OF_SOJOURNER_4P_HANDLER_KEY,
        version=RESOLUTION_OF_SOJOURNER_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            ResolutionOfSojournerChargedCritProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                crit_rate=crit_rate,
            ),
        ),
        metadata={"piece_count": 4, "purpose": "resolution_of_sojourner_4p"},
    )


class ResolutionOfSojournerChargedCritProvider:
    """4 件套：装备者的重击暴击率提升。

    ``crit_rate_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(self, *, owner_ref: str, slot: int, crit_rate: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._crit_rate = crit_rate
        self._provider_key = f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}.4p.charged_crit.slot:{slot}"
        self._source_ref = _source_ref("4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.CRIT_RATE_ADD}),
            owner_ref=self._owner_ref,
            display_name="行者之心 4件套",
        )

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
        if request.main_attack_tag != CHARGED_ATTACK_MAIN_ATTACK_TAG:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.CRIT_RATE_ADD,
                value=self._crit_rate,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(RESOLUTION_OF_SOJOURNER_4P_AUDIT_TAG,),
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
        f"{RESOLUTION_OF_SOJOURNER_KEY_PREFIX}:{scope}:slot:{slot}",
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
