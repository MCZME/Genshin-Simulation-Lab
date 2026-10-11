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

from genshin_sim.content.artifacts._common import (
    FRAMES_PER_SECOND,
    content_source_ref,
    parse_component_values,
    require_piece_count,
    require_set_row,
    slot_owner_ref,
)
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

MAIDEN_BELOVED_KEY_PREFIX = "artifact.maiden_beloved"
MAIDEN_BELOVED_HANDLER_KEY = MAIDEN_BELOVED_KEY_PREFIX
MAIDEN_BELOVED_2P_HANDLER_KEY = f"{MAIDEN_BELOVED_KEY_PREFIX}.2p"
MAIDEN_BELOVED_4P_HANDLER_KEY = f"{MAIDEN_BELOVED_KEY_PREFIX}.4p"
MAIDEN_BELOVED_CONTENT_VERSION = "release"

MAIDEN_BELOVED_4P_TERM_KEY = f"{MAIDEN_BELOVED_KEY_PREFIX}.4p.incoming_healing"


def maiden_beloved_4p_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的 Buff 定义键。"""

    return f"{MAIDEN_BELOVED_KEY_PREFIX}.4p.incoming_healing.slot:{slot}"


def maiden_beloved_4p_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的冲突键，保证不同穿戴者独立叠加。"""

    return f"{MAIDEN_BELOVED_KEY_PREFIX}.4p.slot:{slot}"


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
        self.hook_key = f"{MAIDEN_BELOVED_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = MAIDEN_BELOVED_4P_HANDLER_KEY
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


def create_maiden_beloved_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """被怜爱的少女套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=MAIDEN_BELOVED_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MAIDEN_BELOVED_HANDLER_KEY,
        version=MAIDEN_BELOVED_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "maiden_beloved_set_identity"},
    )


def create_maiden_beloved_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """被怜爱的少女 2 件套：治疗加成提升。"""

    require_piece_count(request, expected=2, handler_key=MAIDEN_BELOVED_2P_HANDLER_KEY)
    (healing_bonus,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套治疗加成",
    )
    owner_ref = slot_owner_ref(request.slot)
    subject_ref = AttributeSubjectRef.character(owner_ref)
    provider_key = f"{MAIDEN_BELOVED_KEY_PREFIX}.2p.healing_bonus.slot:{request.slot}"
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
                source_ref=content_source_ref(MAIDEN_BELOVED_KEY_PREFIX, "2p", request.slot),
                audit_tags=("maiden_beloved_2p",),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=MAIDEN_BELOVED_2P_HANDLER_KEY,
        version=MAIDEN_BELOVED_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "maiden_beloved_2p"},
    )


def create_maiden_beloved_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """被怜爱的少女 4 件套：施放战技/爆发后全队受治疗加成提升。"""

    require_piece_count(request, expected=4, handler_key=MAIDEN_BELOVED_4P_HANDLER_KEY)
    duration_seconds, incoming_bonus = parse_component_values(
        request.params,
        count=2,
        purpose="4 件套全队受治疗加成",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = slot_owner_ref(request.slot)
    definition_key = maiden_beloved_4p_definition_key(request.slot)
    hook = MaidenBelovedPartyHealingBuffHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        incoming_bonus=incoming_bonus,
        definition_key=definition_key,
        term_key=MAIDEN_BELOVED_4P_TERM_KEY,
        source_key=f"{MAIDEN_BELOVED_KEY_PREFIX}:4p:slot:{request.slot}",
    )
    definition = BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{MAIDEN_BELOVED_KEY_PREFIX}.4p",
        handler_key=MAIDEN_BELOVED_4P_HANDLER_KEY,
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
        handler_key=MAIDEN_BELOVED_4P_HANDLER_KEY,
        version=MAIDEN_BELOVED_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "maiden_beloved_4p"},
    )
