"""沉沦之心圣遗物套装实现。

效果与落点：

- 2 件套：获得 15% 水元素伤害加成 -> ``bonus.damage.hydro``
  ``flat_add``，静态绑定穿戴者。
- 4 件套：施放元素战技后的 15 秒内，普通攻击与重击造成的伤害提高 30% ->
  两段协作：窗口状态由挂在穿戴者身上的标记 Buff 承载（900 帧），
  伤害 provider 经装配期注入的 ``TargetBuffPresenceReadPort`` 查窗口
  存在性，命中时贡献 ``damage_bonus_add``。

行为约定：

- 4 件套触发以 ``ACTION_STARTED`` 的 ``ability_key``（``elemental_skill``）
  为准，``owner_slot`` 必须等于穿戴者槽位；窗口只作用于穿戴者本人，
  按槽位独立（不同穿戴者的窗口互不干扰）。
- 「普通攻击与重击」按内容层攻击标签约定识别：普通攻击标签形如
  ``"普通攻击N"``（各角色普攻段数逐段编号），重击标签固定为
  ``"重击"``；伤害 provider 用前缀匹配承接全部普攻段。
- 伤害 provider 自筛公式：``damage_bonus_add`` 只属于通用公式，越界
  阶段会被 ``validate_formula_modifier_stages`` 硬拒绝并让整次结算失败。
"""

from __future__ import annotations

from genshin_sim.content.artifacts._common import (
    CHARGED_ATTACK_MAIN_ATTACK_TAG,
    FRAMES_PER_SECOND,
    NORMAL_ATTACK_TAG_PREFIX,
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
    BONUS_DAMAGE_HYDRO,
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
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

HEART_OF_DEPTH_KEY_PREFIX = "artifact.heart_of_depth"
HEART_OF_DEPTH_HANDLER_KEY = HEART_OF_DEPTH_KEY_PREFIX
HEART_OF_DEPTH_2P_HANDLER_KEY = f"{HEART_OF_DEPTH_KEY_PREFIX}.2p"
HEART_OF_DEPTH_4P_HANDLER_KEY = f"{HEART_OF_DEPTH_KEY_PREFIX}.4p"
HEART_OF_DEPTH_CONTENT_VERSION = "release"

HEART_OF_DEPTH_2P_AUDIT_TAG = "heart_of_depth_2p"
HEART_OF_DEPTH_4P_AUDIT_TAG = "heart_of_depth_4p"


def heart_of_depth_4p_window_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的窗口标记 Buff 定义键。"""

    return f"{HEART_OF_DEPTH_KEY_PREFIX}.4p.window.slot:{slot}"


def heart_of_depth_4p_window_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的窗口冲突键。"""

    return f"{HEART_OF_DEPTH_KEY_PREFIX}.4p.window.slot:{slot}"


def create_heart_of_depth_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """沉沦之心套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    require_set_row(request, handler_key=HEART_OF_DEPTH_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=HEART_OF_DEPTH_HANDLER_KEY,
        version=HEART_OF_DEPTH_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "heart_of_depth_set_identity"},
    )


def create_heart_of_depth_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """沉沦之心 2 件套：获得水元素伤害加成。"""

    require_piece_count(
        request,
        expected=2,
        handler_key=HEART_OF_DEPTH_2P_HANDLER_KEY,
    )
    (hydro_bonus,) = parse_component_values(
        request.params,
        count=1,
        purpose="2 件套水元素伤害加成",
    )
    subject_ref = AttributeSubjectRef.character(slot_owner_ref(request.slot))
    provider_key = f"{HEART_OF_DEPTH_KEY_PREFIX}.2p.hydro_bonus.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({BONUS_DAMAGE_HYDRO}),
            owner_ref=subject_ref,
            display_name="沉沦之心 2件套",
        ),
        (
            ModifierTerm(
                target_key=BONUS_DAMAGE_HYDRO,
                stage=ModifierStage.FLAT_ADD,
                value=hydro_bonus,
                provider_key=provider_key,
                source_ref=content_source_ref(HEART_OF_DEPTH_KEY_PREFIX, "2p", request.slot),
                audit_tags=(HEART_OF_DEPTH_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=HEART_OF_DEPTH_2P_HANDLER_KEY,
        version=HEART_OF_DEPTH_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "heart_of_depth_2p"},
    )


def create_heart_of_depth_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """沉沦之心 4 件套：施放战技后普攻/重击增伤窗口。"""

    require_piece_count(
        request,
        expected=4,
        handler_key=HEART_OF_DEPTH_4P_HANDLER_KEY,
    )
    duration_seconds, na_ca_bonus = parse_component_values(
        request.params,
        count=2,
        purpose="4 件套持续时间/普攻重击增伤",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = slot_owner_ref(request.slot)
    definition_key = heart_of_depth_4p_window_definition_key(request.slot)
    hook = HeartOfDepthSkillCastHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        definition_key=definition_key,
    )
    definition = _build_window_marker_definition(definition_key, request.slot)
    provider = HeartOfDepthNaCaBonusProvider(
        owner_ref=owner_ref,
        slot=request.slot,
        window_definition_key=definition_key,
        bonus=na_ca_bonus,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=HEART_OF_DEPTH_4P_HANDLER_KEY,
        version=HEART_OF_DEPTH_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        damage_modifier_providers=(provider,),
        metadata={"piece_count": 4, "purpose": "heart_of_depth_4p"},
    )


def _build_window_marker_definition(definition_key: str, slot: int) -> BuffDefinition:
    """4 件套窗口标记 Buff 定义；只承载「窗口开着」，数值由伤害 provider 贡献。

    ``marker_only=True`` 时不得声明 ``attribute_modifiers``（框架双向校验）。
    """

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{HEART_OF_DEPTH_KEY_PREFIX}.4p.window",
        handler_key=HEART_OF_DEPTH_4P_HANDLER_KEY,
        conflict_key=heart_of_depth_4p_window_conflict_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        display_name="沉沦之心 4件套·普攻重击增伤窗口",
    )


class HeartOfDepthSkillCastHook:
    """4 件套触发侧：穿戴者施放元素战技后开启 15 秒增伤窗口。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        definition_key: str,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套窗口必须是正帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.CONTENT,
            f"{HEART_OF_DEPTH_KEY_PREFIX}:4p:slot:{slot}",
        )
        self.hook_key = f"{HEART_OF_DEPTH_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = HEART_OF_DEPTH_4P_HANDLER_KEY
        self.subscriptions = ("ACTION_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        payload = getattr(event, "payload", None)
        if payload is None or getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        if getattr(payload, "ability_key", None) != "elemental_skill":
            return HookResult()
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}:window",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=self._owner_subject_ref,
                    source_context=self._source_ref,
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(),
                ),
            ),
        )


class HeartOfDepthNaCaBonusProvider:
    """4 件套：窗口内装备者的普通攻击与重击伤害提升。

    窗口存在性由挂在穿戴者身上的标记 Buff 承载，provider 只读存在性。
    普通攻击按内容层约定逐段编号（``"普通攻击N"``），用前缀匹配承接。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        window_definition_key: str,
        bonus: float,
    ) -> None:
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._window_definition_key = window_definition_key
        self._bonus = bonus
        self._provider_key = f"{HEART_OF_DEPTH_KEY_PREFIX}.4p.na_ca_bonus.slot:{slot}"
        self._source_ref = content_source_ref(HEART_OF_DEPTH_KEY_PREFIX, "4p", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="沉沦之心 4件套·普攻重击增伤",
        )
        self._target_status_port: TargetBuffPresenceReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        target_status_port: TargetBuffPresenceReadPort,
    ) -> None:
        """装配期注入目标状态只读端口；未绑定时不贡献。"""

        self._target_status_port = target_status_port

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
        if not _is_normal_or_charged_attack(request.main_attack_tag):
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=self._owner_ref,
            definition_key=self._window_definition_key,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(HEART_OF_DEPTH_4P_AUDIT_TAG,),
            ),
        )


def _is_normal_or_charged_attack(main_attack_tag: str) -> bool:
    """按内容层攻击标签约定判定普通攻击与重击伤害。"""

    if main_attack_tag == CHARGED_ATTACK_MAIN_ATTACK_TAG:
        return True
    return main_attack_tag.startswith(NORMAL_ATTACK_TAG_PREFIX)
