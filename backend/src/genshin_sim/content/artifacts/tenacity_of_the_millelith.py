"""千岩牢固圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:15017``）；
套装命名采用官方英文名 Tenacity of the Millelith（meropide.cn/en/artifacts）。

效果与落点：

- 2 件套：生命值提升 20% -> ``stat.hp.max`` ``percent_add``，静态绑定
  穿戴者。
- 4 件套：元素战技命中敌人后，队伍中所有角色攻击力提升 20%，护盾强效
  提升 30%，持续 3 秒 -> 全队双属性 Buff（``stat.atk.total``
  ``percent_add`` + ``bonus.shield.strength`` ``flat_add``），180 帧。

行为约定：

- 4 件套触发以 ``DAMAGE_RESOLVED`` 事实承接：``result.main_attack_tag``
  必须是 ``"元素战技"`` 且 ``result.source_ref`` 等于穿戴者，即「元素战技
  命中敌人」。装备者处于后台同样成立（判定只依赖归属，不读取出战状态）。
- 文案没有「不可叠加」条款：不同穿戴者的 4 件套效果按槽位独立定义、
  可同时存在并叠加（与少女 4 件套同一约定）；同一穿戴者的重复命中按
  刷新处理。
- 文案的「每 0.5 秒至多触发一次」内部冷却不做独立建模：Buff 本身
  ``max_stacks=1`` 且按刷新处理，重复触发只刷新持续时间，不产生数值
  叠加；与带冷却建模的差异仅剩过期时刻的细节，不影响面板语义。
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
    BONUS_SHIELD_STRENGTH,
    STAT_ATK_TOTAL,
    STAT_HP_MAX,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)

TENACITY_OF_THE_MILLELITH_KEY_PREFIX = "artifact.tenacity_of_the_millelith"
TENACITY_OF_THE_MILLELITH_HANDLER_KEY = TENACITY_OF_THE_MILLELITH_KEY_PREFIX
TENACITY_OF_THE_MILLELITH_2P_HANDLER_KEY = f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.2p"
TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY = f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p"
TENACITY_OF_THE_MILLELITH_CONTENT_VERSION = "release"

TENACITY_OF_THE_MILLELITH_2P_AUDIT_TAG = "tenacity_of_the_millelith_2p"
TENACITY_OF_THE_MILLELITH_4P_AUDIT_TAG = "tenacity_of_the_millelith_4p"

FRAMES_PER_SECOND = 60

ELEMENTAL_SKILL_MAIN_ATTACK_TAG = "元素战技"

TENACITY_OF_THE_MILLELITH_4P_ATK_TERM_KEY = f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p.atk_percent"
TENACITY_OF_THE_MILLELITH_4P_SHIELD_TERM_KEY = (
    f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p.shield_strength"
)


def tenacity_of_the_millelith_4p_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的 Buff 定义键。"""

    return f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p.party_buff.slot:{slot}"


def tenacity_of_the_millelith_4p_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的冲突键，保证不同穿戴者独立叠加。"""

    return f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p.slot:{slot}"


def create_tenacity_of_the_millelith_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """千岩牢固套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=TENACITY_OF_THE_MILLELITH_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=TENACITY_OF_THE_MILLELITH_HANDLER_KEY,
        version=TENACITY_OF_THE_MILLELITH_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "tenacity_of_the_millelith_set_identity"},
    )


def create_tenacity_of_the_millelith_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """千岩牢固 2 件套：生命值提升。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=TENACITY_OF_THE_MILLELITH_2P_HANDLER_KEY,
    )
    (hp_percent,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套生命值加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.2p.hp_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_HP_MAX}),
            owner_ref=subject_ref,
            display_name="千岩牢固 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_HP_MAX,
                stage=ModifierStage.PERCENT_ADD,
                value=hp_percent,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(TENACITY_OF_THE_MILLELITH_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=TENACITY_OF_THE_MILLELITH_2P_HANDLER_KEY,
        version=TENACITY_OF_THE_MILLELITH_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "tenacity_of_the_millelith_2p"},
    )


def create_tenacity_of_the_millelith_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """千岩牢固 4 件套：战技命中后全队攻击力与护盾强效提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY,
    )
    atk_percent, shield_strength, duration_seconds, _icd_seconds = _parse_component_values(
        request.params,
        count=4,
        purpose="4 件套攻击力/护盾强效/持续时间/内部冷却",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = _owner_ref(request.slot)
    definition_key = tenacity_of_the_millelith_4p_definition_key(request.slot)
    hook = TenacityOfTheMillelithSkillHitHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        atk_bonus=atk_percent,
        shield_bonus=shield_strength,
        definition_key=definition_key,
    )
    definition = _build_party_buff_definition(definition_key, request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY,
        version=TENACITY_OF_THE_MILLELITH_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "tenacity_of_the_millelith_4p"},
    )


def _build_party_buff_definition(
    definition_key: str,
    slot: int,
) -> BuffDefinition:
    """4 件套全队攻击力+护盾强效 Buff 定义；按槽位区分，独立叠加。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}.4p.party_buff",
        handler_key=TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY,
        conflict_key=tenacity_of_the_millelith_4p_conflict_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="千岩牢固 4件套",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=TENACITY_OF_THE_MILLELITH_4P_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                audit_tags=(TENACITY_OF_THE_MILLELITH_4P_AUDIT_TAG,),
            ),
            BuffAttributeModifierTemplate(
                term_key=TENACITY_OF_THE_MILLELITH_4P_SHIELD_TERM_KEY,
                target_key=BONUS_SHIELD_STRENGTH,
                stage=ModifierStage.FLAT_ADD,
                audit_tags=(TENACITY_OF_THE_MILLELITH_4P_AUDIT_TAG,),
            ),
        ),
    )


class TenacityOfTheMillelithSkillHitHook:
    """4 件套：穿戴者的元素战技命中敌人后为全队施加增益 Buff。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        atk_bonus: float,
        shield_bonus: float,
        definition_key: str,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套持续时间必须是正帧数")
        if not math.isfinite(atk_bonus) or atk_bonus <= 0:
            raise ContentUnitValidationError("4 件套攻击力加成必须为正数")
        if not math.isfinite(shield_bonus) or shield_bonus <= 0:
            raise ContentUnitValidationError("4 件套护盾强效加成必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._atk_bonus = atk_bonus
        self._shield_bonus = shield_bonus
        self._definition_key = definition_key
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.CONTENT,
            f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}:4p:slot:{slot}",
        )
        self.hook_key = f"{TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = TENACITY_OF_THE_MILLELITH_4P_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        result = getattr(payload, "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "main_attack_tag", None) != ELEMENTAL_SKILL_MAIN_ATTACK_TAG:
            return HookResult()
        source_ref = getattr(result, "source_ref", None)
        if not isinstance(source_ref, AttributeSubjectRef):
            return HookResult()
        if source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return HookResult()
        if source_ref != self._owner_subject_ref:
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
                definition_key=self._definition_key,
                target_ref=AttributeSubjectRef.character(character.combat_entity_id),
                source_context=self._source_ref,
                duration_frames=self._duration_frames,
                applier_ref=self._owner_subject_ref,
                modifier_values=(
                    BuffModifierValue(
                        term_key=TENACITY_OF_THE_MILLELITH_4P_ATK_TERM_KEY,
                        value=self._atk_bonus,
                    ),
                    BuffModifierValue(
                        term_key=TENACITY_OF_THE_MILLELITH_4P_SHIELD_TERM_KEY,
                        value=self._shield_bonus,
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
        f"{TENACITY_OF_THE_MILLELITH_KEY_PREFIX}:{scope}:slot:{slot}",
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
