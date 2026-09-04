"""被怜爱的少女圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:14004``）。

- 2 件套：角色造成的治疗效果提升 15% -> ``bonus.healing.outgoing``
  ``flat_add`` 0.15，静态绑定穿戴者。
- 4 件套：施放元素战技或元素爆发后的 10 秒内，队伍中所有角色受治疗
  效果加成提高 20% -> 全队 ``bonus.healing.incoming`` ``flat_add`` 0.2
  Buff，持续 600 帧，重复施放按刷新处理。

行为约定：

- 4 件套触发以 ``ACTION_STARTED`` 的 ``ability_key``（``elemental_skill`` /
  ``elemental_burst``）为准，``owner_slot`` 必须等于穿戴者槽位。
- 不同穿戴者的 4 件套效果相互独立：每个槽位拥有自己的 Buff 定义与冲突
  键，各自施放时为自己对应的实例刷新，多个穿戴者的实例可同时存在并
  叠加。
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
    BONUS_HEALING_INCOMING,
    BONUS_HEALING_OUTGOING,
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

MAIDEN_BELOVED_HANDLER_KEY = "artifact.maiden_beloved"
MAIDEN_BELOVED_ASSET_KEY = "artifact_set:14004"
MAIDEN_BELOVED_CONTENT_VERSION = "dev-maiden-beloved"

MAIDEN_BELOVED_4P_TERM_KEY = f"{MAIDEN_BELOVED_HANDLER_KEY}.4p.incoming_healing"

FRAMES_PER_SECOND = 60


def maiden_beloved_4p_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的 Buff 定义键。"""

    return f"{MAIDEN_BELOVED_HANDLER_KEY}.4p.incoming_healing.slot:{slot}"


def maiden_beloved_4p_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的冲突键，保证不同穿戴者独立叠加。"""

    return f"{MAIDEN_BELOVED_HANDLER_KEY}.4p.slot:{slot}"


class MaidenBelovedPartyHealingBuffHook:
    """4 件套：穿戴者施放战技/爆发后为全队施加受治疗加成 Buff。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        incoming_bonus: float,
        definition_key: str,
        term_key: str,
        source_key: str,
    ) -> None:
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._incoming_bonus = incoming_bonus
        self._definition_key = definition_key
        self._term_key = term_key
        self._source_key = source_key
        self.hook_key = f"{MAIDEN_BELOVED_HANDLER_KEY}.4p:{owner_ref}"
        self.state_key = MAIDEN_BELOVED_HANDLER_KEY
        self.subscriptions = ("ACTION_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        if payload is None or getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        if getattr(payload, "ability_key", None) not in {"elemental_skill", "elemental_burst"}:
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
                source_context=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    self._source_key,
                ),
                duration_frames=self._duration_frames,
                applier_ref=AttributeSubjectRef.character(self._owner_ref),
                modifier_values=(
                    BuffModifierValue(
                        term_key=self._term_key,
                        value=self._incoming_bonus,
                    ),
                ),
            )
            for index, character in enumerate(characters)
        )
        return HookResult(buff_requests=requests)


def create_maiden_beloved_content_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """把少女套装效果 payload 编译为 ContentUnit（按件数分支）。"""

    if request.artifact_key != MAIDEN_BELOVED_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{MAIDEN_BELOVED_HANDLER_KEY} 只接受被怜爱的少女资产：{request.artifact_key}"
        )
    if request.artifact_kind != "artifact_set_bonus":
        raise ContentUnitValidationError(
            f"{MAIDEN_BELOVED_HANDLER_KEY} 只绑定套装效果，不绑定套装行"
        )
    if request.piece_count == 2:
        return _create_two_piece_unit(request)
    if request.piece_count == 4:
        return _create_four_piece_unit(request)
    raise ContentUnitValidationError(
        f"{MAIDEN_BELOVED_HANDLER_KEY} 不支持 {request.piece_count} 件套"
    )


def _create_two_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    (healing_bonus,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套治疗加成",
    )
    owner_ref = f"character:slot_{request.slot}"
    subject_ref = AttributeSubjectRef.character(owner_ref)
    provider_key = f"{MAIDEN_BELOVED_HANDLER_KEY}.2p.healing_bonus.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({BONUS_HEALING_OUTGOING}),
            owner_ref=subject_ref,
            display_name="少女飘摇的思念 2件套",
        ),
        (
            ModifierTerm(
                target_key=BONUS_HEALING_OUTGOING,
                stage=ModifierStage.FLAT_ADD,
                value=healing_bonus,
                provider_key=provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    f"{MAIDEN_BELOVED_HANDLER_KEY}:2p:slot:{request.slot}",
                ),
                audit_tags=("maiden_beloved_2p",),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MAIDEN_BELOVED_HANDLER_KEY,
        version=MAIDEN_BELOVED_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "maiden_beloved_2p"},
    )


def _create_four_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    duration_seconds, incoming_bonus = _parse_component_values(
        request.params,
        count=2,
        purpose="4 件套全队受治疗加成",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = f"character:slot_{request.slot}"
    definition_key = maiden_beloved_4p_definition_key(request.slot)
    hook = MaidenBelovedPartyHealingBuffHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        incoming_bonus=incoming_bonus,
        definition_key=definition_key,
        term_key=MAIDEN_BELOVED_4P_TERM_KEY,
        source_key=f"{MAIDEN_BELOVED_HANDLER_KEY}:4p:slot:{request.slot}",
    )
    definition = BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{MAIDEN_BELOVED_HANDLER_KEY}.4p",
        handler_key=MAIDEN_BELOVED_HANDLER_KEY,
        conflict_key=maiden_beloved_4p_conflict_key(request.slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="少女飘摇的思念 4件套",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=MAIDEN_BELOVED_4P_TERM_KEY,
                target_key=BONUS_HEALING_INCOMING,
                stage=ModifierStage.FLAT_ADD,
                audit_tags=("maiden_beloved_4p",),
            ),
        ),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MAIDEN_BELOVED_HANDLER_KEY,
        version=MAIDEN_BELOVED_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "maiden_beloved_4p"},
    )


def _parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
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
