"""昔日宗室之仪圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:15007``）；
套装命名采用官方英文名 Noblesse Oblige（meropide.cn/en/artifacts）。

效果与落点：

- 2 件套：元素爆发造成的伤害提升 20% -> 通用公式
  ``damage_bonus_add`` 阶段，按 ``main_attack_tag == "元素爆发"`` 过滤，
  静态绑定穿戴者，不落 Buff。
- 4 件套：施放元素爆发后，队伍中所有角色攻击力提升 20%，持续 12 秒 ->
  全队 ``stat.atk.total`` ``percent_add`` Buff，720 帧。

行为约定：

- 4 件套触发以 ``ACTION_STARTED`` 的 ``ability_key``（``elemental_burst``）
  为准，``owner_slot`` 必须等于穿戴者槽位。
- 文案明确「该效果不可叠加」：4 件套 Buff 使用**不按槽位区分**的单一
  定义键与冲突键，多个穿戴者的施放互相替换而非叠加（刻意区别于少女
  4 件套的按槽位独立叠加）。重复施放按刷新处理。
- 2 件套只作用于「本次伤害是否由元素爆发产生」的瞬时判定，与 4 件套
  Buff 的加成窗口互不耦合。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.models import HookResult
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

NOBLESSE_OBLIGE_KEY_PREFIX = "artifact.noblesse_oblige"
NOBLESSE_OBLIGE_HANDLER_KEY = NOBLESSE_OBLIGE_KEY_PREFIX
NOBLESSE_OBLIGE_2P_HANDLER_KEY = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.2p"
NOBLESSE_OBLIGE_4P_HANDLER_KEY = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.4p"
NOBLESSE_OBLIGE_CONTENT_VERSION = "release"

NOBLESSE_OBLIGE_2P_AUDIT_TAG = "noblesse_oblige_2p"
NOBLESSE_OBLIGE_4P_AUDIT_TAG = "noblesse_oblige_4p"

FRAMES_PER_SECOND = 60

ELEMENTAL_BURST_MAIN_ATTACK_TAG = "元素爆发"

# 4 件套「不可叠加」：定义键与冲突键都不按槽位区分，全队共享一份窗口。
NOBLESSE_OBLIGE_4P_TERM_KEY = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.4p.atk_percent"
NOBLESSE_OBLIGE_4P_DEFINITION_KEY = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.4p.atk_percent"
NOBLESSE_OBLIGE_4P_CONFLICT_KEY = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.4p.atk_percent"


def create_noblesse_oblige_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """昔日宗室之仪套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=NOBLESSE_OBLIGE_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=NOBLESSE_OBLIGE_HANDLER_KEY,
        version=NOBLESSE_OBLIGE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "noblesse_oblige_set_identity"},
    )


def create_noblesse_oblige_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """昔日宗室之仪 2 件套：元素爆发造成的伤害提升。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=NOBLESSE_OBLIGE_2P_HANDLER_KEY,
    )
    (burst_bonus,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套元素爆发伤害加成",
    )
    owner_ref = _owner_ref(request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=NOBLESSE_OBLIGE_2P_HANDLER_KEY,
        version=NOBLESSE_OBLIGE_CONTENT_VERSION,
        slot=request.slot,
        damage_modifier_providers=(
            NoblesseObligeBurstDamageProvider(
                owner_ref=owner_ref,
                slot=request.slot,
                bonus=burst_bonus,
            ),
        ),
        metadata={"piece_count": 2, "purpose": "noblesse_oblige_2p"},
    )


def create_noblesse_oblige_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """昔日宗室之仪 4 件套：施放元素爆发后全队攻击力提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=NOBLESSE_OBLIGE_4P_HANDLER_KEY,
    )
    atk_percent, duration_seconds = _parse_component_values(
        request.params,
        count=2,
        purpose="4 件套攻击力加成/持续时间",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = _owner_ref(request.slot)
    hook = NoblesseObligeBurstCastHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        atk_bonus=atk_percent,
        term_key=NOBLESSE_OBLIGE_4P_TERM_KEY,
    )
    definition = _build_party_atk_buff_definition()
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=NOBLESSE_OBLIGE_4P_HANDLER_KEY,
        version=NOBLESSE_OBLIGE_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "noblesse_oblige_4p"},
    )


def _build_party_atk_buff_definition() -> BuffDefinition:
    """4 件套全队攻击力 Buff 定义；定义键与冲突键全队共享，保证不可叠加。"""

    return BuffDefinition(
        definition_key=NOBLESSE_OBLIGE_4P_DEFINITION_KEY,
        mechanic_key=f"{NOBLESSE_OBLIGE_KEY_PREFIX}.4p.atk_percent",
        handler_key=NOBLESSE_OBLIGE_4P_HANDLER_KEY,
        conflict_key=NOBLESSE_OBLIGE_4P_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="昔日宗室之仪 4件套",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=NOBLESSE_OBLIGE_4P_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                audit_tags=(NOBLESSE_OBLIGE_4P_AUDIT_TAG,),
            ),
        ),
    )


class NoblesseObligeBurstDamageProvider:
    """2 件套：装备者造成的元素爆发伤害提升。

    ``damage_bonus_add`` 只属于通用公式；必须自筛公式，否则会在反应伤害
    查询上被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
    """

    def __init__(self, *, owner_ref: str, slot: int, bonus: float) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._bonus = bonus
        self._provider_key = f"{NOBLESSE_OBLIGE_KEY_PREFIX}.2p.burst_damage.slot:{slot}"
        self._source_ref = _source_ref("2p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="昔日宗室之仪 2件套",
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
        if request.main_attack_tag != ELEMENTAL_BURST_MAIN_ATTACK_TAG:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(NOBLESSE_OBLIGE_2P_AUDIT_TAG,),
            ),
        )


class NoblesseObligeBurstCastHook:
    """4 件套：穿戴者施放元素爆发后为全队施加攻击力 Buff。

    Buff 定义键与冲突键全队共享，多个穿戴者的施放互相替换（不可叠加）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        atk_bonus: float,
        term_key: str,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套持续时间必须是正帧数")
        if not math.isfinite(atk_bonus) or atk_bonus <= 0:
            raise ContentUnitValidationError("4 件套攻击力加成必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._atk_bonus = atk_bonus
        self._term_key = term_key
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.CONTENT,
            f"{NOBLESSE_OBLIGE_KEY_PREFIX}:4p:slot:{slot}",
        )
        self.hook_key = f"{NOBLESSE_OBLIGE_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = NOBLESSE_OBLIGE_4P_HANDLER_KEY
        self.subscriptions = ("ACTION_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        if payload is None or getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        if getattr(payload, "ability_key", None) != "elemental_burst":
            return HookResult()
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        team_state = getattr(context, "states", None)
        characters = tuple(getattr(team_state, "characters", ()))
        if not characters:
            return HookResult()
        requests = tuple(
            ApplyBuffRequest(
                request_id=f"hook:{self.hook_key}:{frame}:{character.combat_entity_id}",
                frame=frame,
                order=index,
                definition_key=NOBLESSE_OBLIGE_4P_DEFINITION_KEY,
                target_ref=AttributeSubjectRef.character(character.combat_entity_id),
                source_context=self._source_ref,
                duration_frames=self._duration_frames,
                applier_ref=self._owner_subject_ref,
                modifier_values=(
                    BuffModifierValue(
                        term_key=self._term_key,
                        value=self._atk_bonus,
                    ),
                ),
            )
            for index, character in enumerate(characters)
        )
        return HookResult(buff_requests=requests)


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
        f"{NOBLESSE_OBLIGE_KEY_PREFIX}:{scope}:slot:{slot}",
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
