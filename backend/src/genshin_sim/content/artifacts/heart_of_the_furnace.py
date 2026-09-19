"""炉火融炼之心圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:15048``）。

效果与落点：

- 2 件套：攻击力提高 18% -> ``stat.atk.total`` 的 ``percent_add``，
  静态绑定穿戴者。
- 4 件套 B1：触发星烁反应或造成星烁反应伤害后的 12 秒内，装备者攻击力
  提高 12% -> 角色作用域 Buff（``stat.atk.total`` + ``percent_add``），
  720 帧，重复触发按 ``REFRESH`` 处理。
- 4 件套 B2：同一窗口内队伍中所有角色造成的星烁反应伤害提升 50% ->
  **标记 Buff 管生命周期 + 伤害 provider 管逻辑**两段协作：
  窗口状态由挂在**队伍作用域主体**的 ``marker_only`` Buff 承载，
  伤害 provider 经装配期注入的 ``TargetBuffPresenceReadPort``
  查该主体是否存在标记 Buff，命中时贡献星烁公式专属阶段
  ``stellar_reaction_bonus_add``。

行为约定：

- 触发条件为「装备者触发星烁反应**或**造成星烁反应伤害」，两个分支分别
  由 ``REACTION_OCCURRED`` 与 ``DAMAGE_RESOLVED`` 事实承接；装备者处于
  后台同样成立（判定只依赖归属，不依赖出战状态）。
- B1 与 B2 共用同一个触发事实，因此由同一个钩子一次性发出两组 Buff 请求，
  避免两个钩子各自判定造成窗口不完全同步。
- B2 的标记 Buff 挂在**队伍作用域主体** ``AttributeSubjectRef.team`` 上：
  单一主体故天然只有一份窗口，对应文案的「同名圣遗物套装产生的伤害加成
  效果无法叠加」。刻意区别于少女 4 件套的「按槽位独立、可叠加」。
- B2 的伤害 provider **不做参与者去重**：星扩散复合路径会为每个参与者
  各取一份该加成，这是「队伍级效果对每个参与者生效」的正确语义。
- 伤害 provider 未绑定运行端口时不贡献，因此装配完成前不会生效。
- 伤害 provider 自筛公式：越界阶段会被 ``_validate_formula_stages``
  硬拒绝并让整次结算失败，而不是静默跳过。
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
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_STELLAR_REACTION
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_REACTION_KEY,
    STELLAR_CONDUCT_TEAM_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)

HEART_OF_THE_FURNACE_HANDLER_KEY = "artifact.heart_of_the_furnace"
HEART_OF_THE_FURNACE_CONTENT_VERSION = "dev-heart-of-the-furnace"

HEART_OF_THE_FURNACE_2P_AUDIT_TAG = "heart_of_the_furnace_2p"
HEART_OF_THE_FURNACE_4P_AUDIT_TAG = "heart_of_the_furnace_4p"

FRAMES_PER_SECOND = 60

# 4 件套触发条件覆盖的星烁反应集合：星超导与星扩散都是「星烁反应」。
STELLAR_REACTION_KEYS = frozenset(
    {
        STELLAR_CONDUCT_REACTION_KEY,
        STELLAR_SWIRL_REACTION_KEY,
    }
)


def heart_of_the_furnace_4p_atk_definition_key(slot: int) -> str:
    """4 件套 B1（装备者攻击力）按穿戴者槽位区分的 Buff 定义键。"""

    return f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.atk_percent.slot:{slot}"


def heart_of_the_furnace_4p_atk_conflict_key(slot: int) -> str:
    """4 件套 B1 的冲突键；按槽位区分，使不同穿戴者的自身加成互不干扰。"""

    return f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.atk.slot:{slot}"


def heart_of_the_furnace_4p_window_definition_key() -> str:
    """4 件套 B2 的标记 Buff 定义键。

    **队伍级单一定义**：不按槽位区分，因为窗口挂在队伍作用域主体上，
    全队只应存在一份；多人穿戴同名套装时天然共享同一窗口（不叠加）。
    """

    return f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.stellar_window"


def heart_of_the_furnace_4p_window_conflict_key() -> str:
    """4 件套 B2 标记 Buff 的冲突键；队伍级单一键。"""

    return f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.stellar_window"


def create_heart_of_the_furnace_content_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """把炉火融炼之心套装效果 payload 编译为 ContentUnit（按件数分支）。"""

    if request.artifact_kind != "artifact_set_bonus":
        raise ContentUnitValidationError(
            f"{HEART_OF_THE_FURNACE_HANDLER_KEY} 只绑定套装效果，不绑定套装行"
        )
    if request.piece_count == 2:
        return _create_two_piece_unit(request)
    if request.piece_count == 4:
        return _create_four_piece_unit(request)
    raise ContentUnitValidationError(
        f"{HEART_OF_THE_FURNACE_HANDLER_KEY} 不支持 {request.piece_count} 件套"
    )


def _owner_ref(slot: int) -> str:
    return f"character:slot_{slot}"


def _source_ref(scope: str, slot: int) -> RuntimeSourceRef:
    return RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{HEART_OF_THE_FURNACE_HANDLER_KEY}:{scope}:slot:{slot}",
    )


def _create_two_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    """2 件套：穿戴者攻击力提高 18%（静态属性）。"""

    (atk_percent,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套攻击力加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.2p.atk_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ATK_TOTAL}),
            owner_ref=subject_ref,
            display_name="炉火融炼之心 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=atk_percent,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(HEART_OF_THE_FURNACE_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=HEART_OF_THE_FURNACE_HANDLER_KEY,
        version=HEART_OF_THE_FURNACE_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "heart_of_the_furnace_2p"},
    )


def _create_four_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    """4 件套：B1 自身攻击力 +12%，B2 全队星烁反应伤害 +50%，共 720 帧。"""

    duration_seconds, atk_percent, stellar_bonus = _parse_component_values(
        request.params,
        count=3,
        purpose="4 件套持续时间/攻击力/星烁增伤",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")

    owner_ref = _owner_ref(request.slot)
    atk_definition_key = heart_of_the_furnace_4p_atk_definition_key(request.slot)
    window_definition_key = heart_of_the_furnace_4p_window_definition_key()

    hook = HeartOfTheFurnaceTriggerHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        atk_bonus=atk_percent,
        atk_definition_key=atk_definition_key,
        window_definition_key=window_definition_key,
        term_key=f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.atk_percent",
    )
    atk_definition = _build_atk_buff_definition(
        definition_key=atk_definition_key,
        conflict_key=heart_of_the_furnace_4p_atk_conflict_key(request.slot),
    )
    window_definition = _build_window_marker_definition(window_definition_key)
    provider = HeartOfTheFurnaceStellarBonusProvider(
        slot=request.slot,
        window_definition_key=window_definition_key,
        bonus=stellar_bonus,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=HEART_OF_THE_FURNACE_HANDLER_KEY,
        version=HEART_OF_THE_FURNACE_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(atk_definition, window_definition),
        damage_modifier_providers=(provider,),
        metadata={"piece_count": 4, "purpose": "heart_of_the_furnace_4p"},
    )


def _build_atk_buff_definition(
    *,
    definition_key: str,
    conflict_key: str,
) -> BuffDefinition:
    """B1：装备者自身攻击力 +12% 的普通属性 Buff 定义。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.atk_percent",
        handler_key=HEART_OF_THE_FURNACE_HANDLER_KEY,
        conflict_key=conflict_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="炉火融炼之心 4件套·攻击力",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.atk_percent",
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                audit_tags=(HEART_OF_THE_FURNACE_4P_AUDIT_TAG,),
            ),
        ),
    )


def _build_window_marker_definition(definition_key: str) -> BuffDefinition:
    """B2：只承载「窗口开着」这一事实的标记 Buff 定义。

    ``marker_only=True`` 时不得声明 ``attribute_modifiers``（框架双向校验）；
    窗口数值本身由伤害 provider 贡献，不经过属性系统。
    """

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.stellar_window",
        handler_key=HEART_OF_THE_FURNACE_HANDLER_KEY,
        conflict_key=heart_of_the_furnace_4p_window_conflict_key(),
        target_kinds=frozenset({AttributeSubjectKind.TEAM}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        display_name="炉火融炼之心 4件套·星烁增伤窗口",
    )


class HeartOfTheFurnaceTriggerHook:
    """4 件套触发侧：装备者触发星烁反应或造成星烁反应伤害时开启 12 秒窗口。

    同一个触发事实同时驱动两段效果，故一次性发出两组请求：

    - B1：给**装备者本人**施加攻击力 Buff（角色作用域，按槽位独立）；
    - B2：给**队伍作用域主体**施加标记 Buff（单主体 → 天然不叠加）。

    「装备者处于后台也能触发」在判定上自然成立：钩子只比对归属，
    不读取出战状态。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        atk_bonus: float,
        atk_definition_key: str,
        window_definition_key: str,
        term_key: str,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套窗口必须是正帧数")
        if not math.isfinite(atk_bonus) or atk_bonus <= 0:
            raise ContentUnitValidationError("4 件套攻击力加成必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._atk_bonus = atk_bonus
        self._atk_definition_key = atk_definition_key
        self._window_definition_key = window_definition_key
        self._term_key = term_key
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._team_subject_ref = AttributeSubjectRef.team(STELLAR_CONDUCT_TEAM_SCOPE)
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.CONTENT,
            f"{HEART_OF_THE_FURNACE_HANDLER_KEY}:4p:slot:{slot}",
        )
        self.hook_key = f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p:{owner_ref}"
        self.state_key = HEART_OF_THE_FURNACE_HANDLER_KEY
        self.subscriptions = (
            "REACTION_OCCURRED",
            "DAMAGE_RESOLVED",
        )
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        payload = getattr(event, "payload", None)
        if payload is None:
            return HookResult()
        trigger_ref = self._resolve_trigger_ref(payload)
        if trigger_ref is None:
            return HookResult()
        if trigger_ref != self._owner_subject_ref:
            return HookResult()
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}:atk",
                    frame=frame,
                    order=0,
                    definition_key=self._atk_definition_key,
                    target_ref=self._owner_subject_ref,
                    source_context=self._source_ref,
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=self._term_key,
                            value=self._atk_bonus,
                        ),
                    ),
                ),
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}:window",
                    frame=frame,
                    order=1,
                    definition_key=self._window_definition_key,
                    target_ref=self._team_subject_ref,
                    source_context=self._source_ref,
                    duration_frames=self._duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(),
                ),
            ),
        )

    def _resolve_trigger_ref(self, payload: object) -> AttributeSubjectRef | None:
        """从事件载荷解析触发者主体；不满足星烁触发条件时返回 None。

        - ``REACTION_OCCURRED``：读 ``occurrence.source_ref``（``ElementalSourceRef``），
          并校验 ``reaction_key`` 属于星烁反应集合（星超导 / 星扩散）。
          ``source_key`` 与角色主体 ``entity_id`` 同格式（``character:slot_N``），
          故可直接映射。
        - ``DAMAGE_RESOLVED``：读 ``result.source_ref``（``AttributeSubjectRef``），
          并校验 ``formula_key`` 为星烁完整公式，用以区分星烁与直伤。
        """

        occurrence = getattr(payload, "occurrence", None)
        if occurrence is not None:
            if occurrence.reaction_key not in STELLAR_REACTION_KEYS:
                return None
            source_ref = getattr(occurrence, "source_ref", None)
            source_key = getattr(source_ref, "source_key", None)
            if not isinstance(source_key, str) or not source_key:
                return None
            return AttributeSubjectRef.character(source_key)
        result = getattr(payload, "result", None)
        if result is None:
            return None
        if getattr(result, "formula_key", None) != FORMULA_KEY_STELLAR_REACTION:
            return None
        source_ref = getattr(result, "source_ref", None)
        if not isinstance(source_ref, AttributeSubjectRef):
            return None
        if source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return None
        return source_ref


class HeartOfTheFurnaceStellarBonusProvider:
    """4 件套 B2：队伍级星烁反应伤害提升。

    窗口存在性由挂在**队伍作用域主体**的标记 Buff 承载，provider 只读
    存在性（``has_buff``），不持有任何状态、不自行计时。

    **不做参与者去重**：星扩散复合路径会为每个参与者各取一份本加成，
    这是「队伍级效果对每个参与者生效」的正确语义（每人基于自身状态结算）。
    """

    def __init__(
        self,
        *,
        slot: int,
        window_definition_key: str,
        bonus: float,
    ) -> None:
        self._slot = slot
        self._window_definition_key = window_definition_key
        self._bonus = bonus
        self._team_subject_ref = AttributeSubjectRef.team(STELLAR_CONDUCT_TEAM_SCOPE)
        self._provider_key = (
            f"{HEART_OF_THE_FURNACE_HANDLER_KEY}.4p.stellar_bonus.slot:{slot}"
        )
        self._source_ref = _source_ref("4p:stellar_bonus", slot)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._team_subject_ref,
            display_name="炉火融炼之心 4件套·星烁增伤",
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
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        del session
        request = query.request
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=self._team_subject_ref,
            definition_key=self._window_definition_key,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(HEART_OF_THE_FURNACE_4P_AUDIT_TAG,),
            ),
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
