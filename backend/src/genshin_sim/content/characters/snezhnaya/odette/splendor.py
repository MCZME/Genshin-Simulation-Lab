"""奥黛塔华彩体系（P4 获选者的春祭）：Buff 定义、发放、后台衰减转交与
星烁伤害修饰。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from genshin_sim.content.characters.snezhnaya.odette.dance import active_dance_reflection
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_SPLENDOR_ATK_TERM_KEY,
    ODETTE_SPLENDOR_BACKGROUND_TICK_FRAMES,
    ODETTE_SPLENDOR_BUFF_MECHANIC_KEY,
    ODETTE_SPLENDOR_DECAY_IMPACT_KEY,
    ODETTE_SPLENDOR_GRANT_IMPACT_KEY,
    ODETTE_SPLENDOR_MAX_STACKS,
    ODETTE_SPLENDOR_TRANSFER_STACK_CAP,
    ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME,
    odette_splendor_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    STELLAR_REACTION_DAMAGE_TAGS,
)
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.impacts.models import ActionImpactContext
from genshin_sim.core.systems.buff.definitions import (
    BuffAttributeModifierTemplate,
    BuffDefinition,
)
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationPolicy,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


class OdetteSplendorError(RuntimeError):
    """华彩体系运行期错误（接线缺失或契约不完整）。"""


@dataclass(frozen=True, slots=True)
class SplendorGrantConfig:
    """召唤发放参数（内容编译期冻结，随角色单元交给影响工厂）。"""

    definition_key: str
    grant_stacks: int
    duration_frames: int
    # APPLY_STATUS 契约要求 modifier_values 与定义模板完整匹配：C2 解锁时
    # 携带攻击力词条值，未解锁时为空（纯层数载体）。
    modifier_values: tuple[dict[str, object], ...]


def build_splendor_buff_definition(
    slot: int,
    *,
    handler_key: str,
    display_name: str,
    atk_per_stack: float | None,
) -> BuffDefinition:
    """编译华彩 Buff 定义。

    定义键按奥黛塔槽位区分、冲突键同值（sandrone 改进战术先例）：同主体
    多次申请收敛于单条记录，不同主体各自持层互不冲突。STACK_REFRESH 策略
    承载转交加层；C2 解锁时携带攻击力词条（PERCENT_ADD + LINEAR 逐层）。
    ``handler_key`` 由贡献单元（P4 效果行）传入——定义只能由同 handler 的
    内容单元贡献（装配期校验）。
    """

    if atk_per_stack is not None and atk_per_stack <= 0.0:
        raise OdetteSplendorError("华彩攻击力词条必须为正数")
    definition_key = odette_splendor_definition_key(slot)
    attribute_modifiers: tuple[BuffAttributeModifierTemplate, ...] = ()
    if atk_per_stack is not None:
        attribute_modifiers = (
            BuffAttributeModifierTemplate(
                term_key=ODETTE_SPLENDOR_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=BuffStackScaling.LINEAR,
            ),
        )
    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=ODETTE_SPLENDOR_BUFF_MECHANIC_KEY,
        handler_key=handler_key,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=ODETTE_SPLENDOR_MAX_STACKS,
        attribute_modifiers=attribute_modifiers,
        marker_only=atk_per_stack is None,
        display_name=display_name,
    )


def summon_grant_requests(
    context: ActionImpactContext,
    config: SplendorGrantConfig,
    *,
    slot: int,
) -> tuple[ImpactRequest, ImpactRequest]:
    """展开召唤发放请求：先清除全部持有者的旧华彩，再给奥黛塔发新层。

    「重新召唤」结束既有华彩（含已转交的层）后按发放层数重新授予——清除
    走 REMOVE_STATUS 的 definition_key 形态（整条移除），对未持层目标是无
    操作；发放走 APPLY_STATUS，期限为召唤物整段持续时间。
    """

    simulation = context.simulation
    if simulation is None or simulation.space_runtime is None:
        raise OdetteSplendorError("缺少空间运行时，无法展开华彩发放请求")
    team_refs = tuple(
        character.combat_entity_id for character in simulation.space_runtime.team_state.characters
    )
    odette_ref = f"character:slot_{slot}"
    frame = context.frame
    reset = ImpactRequest(
        frame=frame,
        kind=ImpactKind.REMOVE_STATUS,
        impact_key=ODETTE_SPLENDOR_GRANT_IMPACT_KEY,
        owner_slot=slot,
        request_id=f"odette.splendor.grant:{frame}:reset",
        target_refs=team_refs,
        params={
            "buff_remove": {"definition_key": config.definition_key},
        },
    )
    grant = ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_STATUS,
        impact_key=ODETTE_SPLENDOR_GRANT_IMPACT_KEY,
        owner_slot=slot,
        request_id=f"odette.splendor.grant:{frame}:apply",
        target_refs=(odette_ref,),
        params={
            "buff": {
                "definition_key": config.definition_key,
                "duration_frames": config.duration_frames,
                "stack_delta": config.grant_stacks,
                "modifier_values": config.modifier_values,
                "applier_ref": AttributeSubjectRef.character(odette_ref).to_dict(),
            },
        },
    )
    return reset, grant


class OdetteSplendorDecayHook:
    """奥黛塔后台时的华彩衰减/转交 hook（FRAME_STARTED 驱动）。

    每秒（59/60 帧交替，59 起步）清除 1 层并转交给其他队伍角色；C6 转交时
    自己的层数不再减少（转交仍以持层为前提）。tick 光标记在角色内容状态
    （0 = 未武装）：切后台时惰性武装，回前台暂停不重置，再次切后台从已
    武装的帧继续。转交申请期限跟随召唤物剩余时间；找不到活动召唤物时跳过
    本 tick（华彩本应随召唤物退场过期）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        definition_key: str,
        layers_per_tick: int,
        keep_own_stacks: bool,
        modifier_values: tuple[dict[str, object], ...],
    ) -> None:
        if not owner_ref.strip():
            raise OdetteSplendorError("华彩衰减 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise OdetteSplendorError("华彩衰减 hook 必须绑定正整数队伍槽位")
        if layers_per_tick <= 0:
            raise OdetteSplendorError("华彩每 tick 清除层数必须是正整数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._definition_key = definition_key
        self._layers_per_tick = layers_per_tick
        self._keep_own_stacks = keep_own_stacks
        self._modifier_values = tuple(dict(item) for item in modifier_values)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.hook_key = f"odette.splendor:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配期注入目标 Buff 只读端口；未绑定时 hook 不产生任何请求。"""

        self._target_status_port = target_status_port

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        if self._target_status_port is None:
            return HookResult()
        if getattr(event, "event_type", None) is not EventType.FRAME_STARTED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if frame <= 0:
            return HookResult()

        hook_context = cast(HookContext, context)
        states = hook_context.states
        if states is None or states.active_slot == self._slot:
            return HookResult()
        state = hook_context.state(self._owner_ref)
        next_tick = _as_int(state.get(ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME))

        if next_tick <= 0:
            return HookResult(
                state_patches=(self._cursor_patch(frame + ODETTE_SPLENDOR_BACKGROUND_TICK_FRAMES),)
            )
        if frame < next_tick:
            return HookResult()
        return self._fire_tick(hook_context, frame)

    def _fire_tick(
        self,
        hook_context: HookContext,
        frame: int,
    ) -> HookResult:
        states = hook_context.states
        assert states is not None
        summon = active_dance_reflection(hook_context.simulation, self._slot)
        advance = self._cursor_patch(frame + ODETTE_SPLENDOR_BACKGROUND_TICK_FRAMES)
        if summon is None:
            return HookResult(state_patches=(advance,))
        expiry = summon.entity.lifecycle.expires_at_frame
        if expiry is None or expiry <= frame:
            return HookResult(state_patches=(advance,))

        assert self._target_status_port is not None
        stacks = self._target_status_port.active_stack_count(
            target_ref=AttributeSubjectRef.character(self._owner_ref),
            definition_key=self._definition_key,
            frame=frame,
        )
        requests: list[ImpactRequest] = []
        if stacks >= 1:
            transfer = (
                self._layers_per_tick
                if self._keep_own_stacks
                else min(self._layers_per_tick, stacks)
            )
            remaining = expiry - frame
            for character in states.characters:
                if character.combat_entity_id == self._owner_ref:
                    continue
                companion_ref = AttributeSubjectRef.character(character.combat_entity_id)
                held = self._target_status_port.active_stack_count(
                    target_ref=companion_ref,
                    definition_key=self._definition_key,
                    frame=frame,
                )
                # 转交到「单次召唤的总发放层数」为止（C6 自身不减层时靠这个
                # 上限兜住，否则会随 tick 无上限累加）。
                delta = min(transfer, ODETTE_SPLENDOR_TRANSFER_STACK_CAP - held)
                if delta <= 0:
                    continue
                requests.append(
                    self._apply_request(frame, character.combat_entity_id, delta, remaining)
                )
            if not self._keep_own_stacks:
                requests.append(self._reduce_request(frame, min(self._layers_per_tick, stacks)))
        return HookResult(
            impact_requests=tuple(requests),
            state_patches=(advance,),
        )

    def _apply_request(
        self,
        frame: int,
        target_ref: str,
        stack_delta: int,
        duration_frames: int,
    ) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_STATUS,
            impact_key=ODETTE_SPLENDOR_DECAY_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{frame}:transfer",
            target_refs=(target_ref,),
            params={
                "buff": {
                    "definition_key": self._definition_key,
                    "duration_frames": duration_frames,
                    "stack_delta": stack_delta,
                    "modifier_values": self._modifier_values,
                    "applier_ref": AttributeSubjectRef.character(self._owner_ref).to_dict(),
                },
            },
        )

    def _reduce_request(self, frame: int, stacks: int) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.REMOVE_STATUS,
            impact_key=ODETTE_SPLENDOR_DECAY_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{frame}:decay",
            target_refs=(self._owner_ref,),
            params={
                "buff_remove": {
                    "definition_key": self._definition_key,
                    "stacks": stacks,
                },
            },
        )

    def _cursor_patch(self, next_tick: int) -> StatePatchRequest:
        return StatePatchRequest(
            owner_ref=self._owner_ref,
            state_key=self.state_key,
            fields={
                ODETTE_STATE_SPLENDOR_NEXT_TICK_FRAME: next_tick,
            },
        )


class OdetteSplendorReactionBonusProvider:
    """P4：华彩持有者造成的星烁反应伤害按层数提升（词条通道）。

    每层 +``bonus_per_stack``（资产 dictionary 华彩词条 props[0] = 0.15）。
    覆盖星超导（冰/雷）与星扩散（冰/风）全部星烁反应伤害——含携带对应
    标签的星变体直伤与反应本体伤害；按**伤害来源**的持有层数折算（转交给
    其他角色后由持有者受益）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        definition_key: str,
        bonus_per_stack: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise OdetteSplendorError("华彩星烁增伤 owner_ref 必须是非空字符串")
        if bonus_per_stack <= 0.0:
            raise OdetteSplendorError("华彩每层星烁增伤必须为正数")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._definition_key = definition_key
        self._bonus_per_stack = bonus_per_stack
        self._provider_key = f"{source_key}.splendor_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配期注入目标 Buff 只读端口；未绑定时 provider 不产出词条。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        if self._target_status_port is None:
            return ()
        request = query.request
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        stacks = self._target_status_port.active_stack_count(
            target_ref=request.source_ref,
            definition_key=self._definition_key,
            frame=request.frame,
        )
        if stacks <= 0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._bonus_per_stack * stacks,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


class OdetteSplendorAscensionProvider:
    """C6：华彩持有者的星烁反应伤害擢升 25%，奥黛塔额外擢升 20%。

    资产 C6 行 number_3/number_4 承载两档数值；按**伤害来源**的持有层数
    判定「处于华彩影响下」（≥1 层），经 ``stellar_ascension_bonus_add``
    词条进入星烁擢升槽位（多个擢升来源互相加算）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        definition_key: str,
        holder_bonus: float,
        self_extra_bonus: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise OdetteSplendorError("华彩擢升 owner_ref 必须是非空字符串")
        if holder_bonus < 0.0 or self_extra_bonus < 0.0:
            raise OdetteSplendorError("华彩擢升不能为负数")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._definition_key = definition_key
        self._holder_bonus = holder_bonus
        self._self_extra_bonus = self_extra_bonus
        self._provider_key = f"{source_key}.splendor_ascension:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配期注入目标 Buff 只读端口；未绑定时 provider 不产出词条。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        if self._target_status_port is None:
            return ()
        request = query.request
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        stacks = self._target_status_port.active_stack_count(
            target_ref=request.source_ref,
            definition_key=self._definition_key,
            frame=request.frame,
        )
        if stacks <= 0:
            return ()
        terms = [
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD,
                value=self._holder_bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        ]
        if request.source_ref == self._owner_ref and self._self_extra_bonus > 0.0:
            terms.append(
                DamageModifierTerm(
                    stage=DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD,
                    value=self._self_extra_bonus,
                    provider_key=self._provider_key,
                    source_ref=self._source_ref,
                ),
            )
        return tuple(terms)


def _as_int(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return 0
    return raw
