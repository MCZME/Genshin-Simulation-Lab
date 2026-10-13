"""generic 通用角色动作解释器。

一般角色的动作解释收敛为一个共享骨架：触发器过滤、输入映射、链状态读取、
下落落地重置、存活判定、左键长按双语义、能力门槛、衔接判定、动作选择
（普攻连段推进 + 连段窗口）、``state_patch`` 提交与 ``PreparedAction`` 构造。
角色包只提供数据（``GenericCharacterActionSpec``）与状态挂载；解释器无实例
可变字段，链状态经 ``state_patch`` 意图提交，与既有解释器口径一致。

链状态生命周期两条规则：

- **存活判定**：链状态里的上一动作只在 ``frame < 起手帧 + duration_frames``
  内代表「在进行的动作」，参与衔接判定；动作结束后按「无前置动作」衔接。
  下落动作豁免帧数判据（由 ``FallPlungeAction`` 承担，按高度存活，落地由
  解释器主流程重置）。
- **连段窗口**：普攻连段推进以上一动作自身 ``duration_frames`` 为窗口（含
  结束帧），窗口外普攻回第一段，连段不无限存活。窗口即动作表已有数据，
  无新增数值。

有独立机制的角色以子类覆写命名挂点接入，挂点默认实现均为无操作。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from genshin_sim.content.generic.chain_state import (
    CHAIN_STATE_LAST_ACTION_KEY,
    CHAIN_STATE_LAST_START_FRAME,
)
from genshin_sim.content.generic.plunge import (
    PLUNGE_HIGH_AIR_HEIGHT,
    PLUNGE_LOW_AIR_HEIGHT,
)
from genshin_sim.content.generic.timed_action import (
    TimedActionSpec,
    build_timed_actions,
)
from genshin_sim.content.generic.transitions import evaluate_transition
from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.actions import (
    Action,
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    ActiveActionLinkView,
    FallPlungeAction,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
)
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.space.entities import SpatialEntity
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.cooldown import CooldownDurationTerm

# 输入种类是全部角色动作解释的公共词汇，字符值与既有内容包一致。
NORMAL_ATTACK_INPUT = "normal_attack"
CHARGED_ATTACK_INPUT = "charged_attack"
ELEMENTAL_SKILL_INPUT = "elemental_skill"
ELEMENTAL_BURST_INPUT = "elemental_burst"
JUMP_INPUT = "jump"
SWITCH_INPUT = "switch"


def switch_offset_frames(spec: TimedActionSpec) -> int | None:
    """派生一个动作的「可切人帧」（相对起手帧的偏移）；无从派生时返回 ``None``。

    动作表尚未逐条声明切人列，按「该动作各衔接列的最早帧」派生，即切换与其它
    输入共用同一份时间口径、不引入新的数值来源。内容取得来源后可显式声明
    ``transitions[SWITCH_INPUT]`` 覆盖派生值。

    整表没有衔接数据（跳跃、下落等）时无可派生帧，返回 ``None`` 由消费方解释为
    「该动作不限制切换」——切人不是动作表里的动作，缺数据不代表禁止切换。
    """

    explicit = spec.transitions.get(SWITCH_INPUT)
    if explicit is not None:
        return explicit
    if not spec.transitions:
        return None
    return min(spec.transitions.values())


class GenericCharacterActionError(RuntimeError):
    """通用角色动作解释器运行期错误（接线缺失或状态不一致）。"""


@dataclass(frozen=True, slots=True)
class GenericAbilityGate:
    """一个输入种类的能力门槛（冷却 / 爆发能量）声明。"""

    input_kind: str
    ability_key: str
    blocked_message: str

    def __post_init__(self) -> None:
        if not self.input_kind.strip():
            msg = "input_kind 必须是非空字符串"
            raise ValueError(msg)
        if not self.ability_key.strip():
            msg = "ability_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.blocked_message.strip():
            msg = "blocked_message 必须是非空字符串"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class GenericCharacterActionSpec:
    """通用角色动作解释器的角色数据面。

    动作表沿用 ``TimedActionSpec``；键均为内容级稳定键。``action_kind_param_name``
    与 ``hit_frame_param_name`` 是动作参数键名（如 ``sucrose_action_kind``），
    由角色影响工厂消费，为既有契约显式声明、不做全局改名。
    """

    display_name: str
    character_handler_key: str
    input_kind_by_session_key: Mapping[str, str]
    action_table: Mapping[str, TimedActionSpec]
    normal_attack_action_keys: tuple[str, ...]
    plunge_action_key: str
    plunge_collision_impact_key: str
    plunge_landing_impact_key: str
    elemental_skill_action_key: str
    elemental_burst_action_key: str
    jump_action_key: str | None = None
    charged_attack_action_key: str | None = None
    hold_input_min_frames: int | None = None
    ability_gates: tuple[GenericAbilityGate, ...] = ()
    action_kind_param_name: str = "action_kind"
    hit_frame_param_name: str = "hit_frame"

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            msg = "display_name 必须是非空字符串"
            raise ValueError(msg)
        if not self.character_handler_key.strip():
            msg = "character_handler_key 必须是非空字符串"
            raise ValueError(msg)
        if not self.action_kind_param_name.strip() or not self.hit_frame_param_name.strip():
            msg = "动作参数键名必须是非空字符串"
            raise ValueError(msg)
        if not self.normal_attack_action_keys:
            msg = "normal_attack_action_keys 不能为空"
            raise ValueError(msg)
        if (self.charged_attack_action_key is None) != (self.hold_input_min_frames is None):
            msg = "charged_attack_action_key 与 hold_input_min_frames 必须同时提供或同时缺省"
            raise ValueError(msg)
        if self.hold_input_min_frames is not None and (
            isinstance(self.hold_input_min_frames, bool) or self.hold_input_min_frames <= 0
        ):
            msg = "hold_input_min_frames 必须是正整数"
            raise ValueError(msg)
        required_keys = {
            "normal_attack_action_keys": self.normal_attack_action_keys,
            "plunge_action_key": (self.plunge_action_key,),
            "elemental_skill_action_key": (self.elemental_skill_action_key,),
            "elemental_burst_action_key": (self.elemental_burst_action_key,),
            "jump_action_key": (() if self.jump_action_key is None else (self.jump_action_key,)),
            "charged_attack_action_key": (
                () if self.charged_attack_action_key is None else (self.charged_attack_action_key,)
            ),
        }
        missing = [
            (field_name, action_key)
            for field_name, keys in required_keys.items()
            for action_key in keys
            if action_key not in self.action_table
        ]
        if missing:
            details = ", ".join(f"{name}={key}" for name, key in missing)
            msg = f"{self.display_name}动作规格引用了动作表中不存在的动作键：{details}"
            raise ValueError(msg)
        for gate in self.ability_gates:
            if not isinstance(gate, GenericAbilityGate):
                msg = "ability_gates 成员必须是 GenericAbilityGate"
                raise ValueError(msg)


class GenericCharacterActionInterpreter:
    """按角色数据面解释一般角色的动作输入。

    子类可覆写的命名挂点（默认全部无操作或直通用途）：

    - ``_input_override``：触发前独占接管任意已映射输入的全部触发器。
      返回 ``None`` 表示不由本挂点处理，落入通用触发器过滤。
    - ``_ability_gate_override``：按输入种类返回 ``(ability_key, 阻断文案)``
      覆写数据面门槛。
    - ``_select_action_override``：覆写动作选择。
    - ``_state_patch_extra_fields``：向连段状态补丁追加字段。
    - ``_cast_frame_effects``：施放帧效果，返回值并入 ``PreparedAction`` 参数。
    - ``_action_kind_value``：覆写动作参数里的动作种类值。
    """

    def __init__(
        self,
        spec: GenericCharacterActionSpec,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
    ) -> None:
        self._spec = spec
        self._action_table = dict(action_table or spec.action_table)

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        input_kind = self._spec.input_kind_by_session_key.get(session.key)
        slot = session.owner.slot
        if input_kind is not None and slot is not None:
            # 触发前独占接管（左键双语义状态机、E 长按自动起手等）先于其他
            # 输入的 PRESS 等待；返回 None 表示不由挂点处理，落入通用路径。
            override_result = self._input_override(context, session, slot, input_kind)
            if override_result is not None:
                return override_result
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")
        if input_kind is None:
            return ActionInterpretationResult.reject(
                f"{self._spec.display_name}不支持输入：{session.key}"
            )
        if slot is None:
            return ActionInterpretationResult.reject(
                f"{self._spec.display_name}动作需要角色归属槽位"
            )

        height = self._current_height(context.simulation)
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if last_action_key == self._spec.plunge_action_key and height <= 0:
            last_action_key = ""
        # 衔接判定的前置动作只在「上一个动作仍在进行」时成立；连段索引仍用
        # 原值（普攻连段推进依赖它，见 _select_normal_attack_action）。
        gate_action_key = self._live_action_key(
            last_action_key,
            last_action_start_frame,
            session.current_frame,
        )

        input_kind = self._resolve_attack_input_kind(
            input_kind,
            session.held_frames,
            plunge=self._is_airborne_plunge(last_action_key, height),
        )

        rejection = self._ability_gate(context, slot, session.current_frame, input_kind)
        if rejection is not None:
            return ActionInterpretationResult.reject(rejection)

        # 衔接判定用当前解释帧（重评路径即为重评帧）：未到最早衔接帧由解释器
        # 交管理器缓冲，查无衔接数据仍为终局拒绝。
        verdict = evaluate_transition(
            action_table=self._action_table,
            display_name=self._spec.display_name,
            prev_action_key=gate_action_key,
            input_kind=input_kind,
            frame=session.current_frame,
            prev_start_frame=last_action_start_frame,
        )
        if verdict.before_earliest:
            return ActionInterpretationResult.defer(verdict.reject_message())
        if verdict.missing_data:
            return ActionInterpretationResult.reject(verdict.reject_message())

        action = self._select_action(
            context,
            slot=slot,
            frame=session.current_frame,
            held_frames=session.held_frames,
            input_kind=input_kind,
            last_action_key=last_action_key,
            last_action_start_frame=last_action_start_frame,
            height=height,
        )
        owner_ref = f"character:slot_{slot}"
        extra_params = self._cast_frame_effects(
            context,
            slot=slot,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            input_kind=input_kind,
        )
        self._queue_state_patch(
            context,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.current_frame,
            input_kind=input_kind,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params={
                    **self._action_params(action, input_kind, height),
                    **extra_params,
                },
                source_session_id=session.session_id,
            )
        )

    # --- 只读衔接视图（供队伍切人判定） -----------------------------------------------

    def read_active_action_link(
        self,
        simulation: SimulationContext,
        slot: int,
    ) -> ActiveActionLinkView:
        """读取该槽位「在进行的动作」的可切人衔接视图（只读，不写状态）。

        复用与输入解释完全相同的链状态读取（``_read_state``）与存活判定
        （``_live_action_key``），因此「切人可用的帧」与「其它输入可衔接的帧」
        同源，不另立时间口径。

        链状态挂载缺失属于装配缺陷，与角色输入解释一致地确定性报错，不静默降级。
        """

        last_action_key, last_action_start_frame = self._read_state(simulation, slot)
        self._validate_known_state(last_action_key)
        height = self._current_height(simulation)
        if last_action_key == self._spec.plunge_action_key and height <= 0:
            last_action_key = ""
        live_action_key = self._live_action_key(
            last_action_key,
            last_action_start_frame,
            simulation.current_frame,
        )
        if not live_action_key:
            return ActiveActionLinkView(active_slot=slot)
        return ActiveActionLinkView(
            active_slot=slot,
            action_key=live_action_key,
            start_frame=last_action_start_frame,
            switch_offset_frames=switch_offset_frames(self._action_table[live_action_key]),
        )

    # --- 挂点（默认无操作或直通） -------------------------------------------------

    def _input_override(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
        input_kind: str,
    ) -> ActionInterpretationResult | None:
        """触发前独占接管；默认不接管。

        覆盖范围是任意已映射输入的全部触发器（按下/长按/松开），用于带会话
        状态的输入语义。返回 ``None`` 表示不由本挂点处理，落入通用触发器过滤。
        """

        return None

    def _ability_gate_override(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
        input_kind: str,
    ) -> tuple[str, str] | None:
        """覆写数据面能力门槛；默认不覆写。"""

        return None

    def _select_action_override(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        frame: int,
        held_frames: int,
        input_kind: str,
        last_action_key: str,
        height: float,
    ) -> TimedActionSpec | None:
        """覆写动作选择；默认不覆写。

        ``held_frames`` 服务点按/长按在选择层改判的形态（如长柄重击骑普攻
        衔接列：衔接判定继续看普攻输入，长按改判只发生在选择层）。
        """

        return None

    def _state_patch_extra_fields(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        frame: int,
        action: TimedActionSpec,
        input_kind: str,
    ) -> Mapping[str, JSONValue]:
        """向连段状态补丁追加字段；默认不追加。"""

        return {}

    def _cast_frame_effects(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        owner_ref: str,
        frame: int,
        session_id: int,
        input_kind: str,
    ) -> Mapping[str, object]:
        """施放帧效果；返回值并入 ``PreparedAction`` 参数，默认无效果。"""

        return {}

    def _action_kind_value(self, *, action: TimedActionSpec, input_kind: str) -> str:
        """动作参数里的动作种类值；默认即输入种类。"""

        return input_kind

    # --- 门槛 ---------------------------------------------------------------------

    def _ability_gate(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
        input_kind: str,
    ) -> str | None:
        """能力门槛（冷却 / 爆发能量）：先问覆写点，再查数据面。

        公共条件端口未接线时不阻断，真实装配必须提供端口。
        """

        override = self._ability_gate_override(context, slot, frame, input_kind)
        if override is not None:
            ability_key, blocked_message = override
        else:
            gate = next(
                (item for item in self._spec.ability_gates if item.input_kind == input_kind),
                None,
            )
            if gate is None:
                return None
            ability_key, blocked_message = gate.ability_key, gate.blocked_message
        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key=ability_key,
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return blocked_message

    # --- 状态 ---------------------------------------------------------------------

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=self._spec.character_handler_key,
            )
        except StateContainerNotFoundError as exc:
            raise GenericCharacterActionError(
                f"缺少{self._spec.display_name}状态挂载：{exc}"
            ) from exc
        raw_key = mount.values.get(CHAIN_STATE_LAST_ACTION_KEY)
        last_key = raw_key if isinstance(raw_key, str) else ""
        raw_start = mount.values.get(CHAIN_STATE_LAST_START_FRAME)
        last_start = (
            raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
        )
        return last_key, last_start

    def _validate_known_state(self, last_action_key: str) -> None:
        """状态损坏时确定性报错，不允许静默重启。"""

        if last_action_key and last_action_key not in self._action_table:
            raise GenericCharacterActionError(
                f"未知{self._spec.display_name}动作状态：{last_action_key}"
            )

    def _queue_state_patch(
        self,
        context: ActionInterpretationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        action: TimedActionSpec,
        start_frame: int,
        input_kind: str,
    ) -> None:
        simulation = context.simulation
        queue = cast(IntentQueue | None, simulation.get_system(IntentQueue))
        if queue is None:
            raise GenericCharacterActionError(
                f"缺少 IntentQueue，无法提交{self._spec.display_name}状态"
            )
        fields: dict[str, JSONValue] = {
            CHAIN_STATE_LAST_ACTION_KEY: action.action_key,
            CHAIN_STATE_LAST_START_FRAME: start_frame,
        }
        fields.update(
            self._state_patch_extra_fields(
                context,
                slot=int(owner_ref.removeprefix("character:slot_")),
                frame=frame,
                action=action,
                input_kind=input_kind,
            )
        )
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"{self._spec.character_handler_key}_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=simulation.settlement_round + 1,
                source_ref=self._spec.character_handler_key,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=self._spec.character_handler_key,
                    fields=fields,
                ),
            )
        )

    # --- 判定 ---------------------------------------------------------------------

    def _live_action_key(
        self,
        last_action_key: str,
        last_action_start_frame: int,
        frame: int,
    ) -> str:
        """连段状态里的动作键只在动作仍在进行时代表「在进行的动作」。

        动作一旦结束（``frame >= 起手帧 + duration_frames``），它不再代表任何
        在进行的动作，衔接判定按「无前置动作」处理。否则拿已结束的动作查衔接
        表时，凡是该行没有对应列的输入都会被判「缺少衔接数据」而**终局拒绝**：
        普攻行没有战技/爆发列，跳跃行整张衔接表为空，于是「普攻后按 E/Q」
        与「跳跃后任何输入」都会永久失效——连段状态在动作结束后并不会被清空。

        只用于衔接判定；普攻连段索引仍要读状态里的原值（否则连段会退回第一段）。
        """

        if not last_action_key:
            return ""
        if last_action_key == self._spec.plunge_action_key:
            # 下落动作由 ``FallPlungeAction`` 承担，动作表里的 ``duration_frames``
            # 是占位值，存活判据是高度而非帧数（落地由 interpret 主流程重置）。
            return last_action_key
        spec_row = self._action_table[last_action_key]
        if frame >= last_action_start_frame + spec_row.duration_frames:
            return ""
        return last_action_key

    def _resolve_attack_input_kind(
        self,
        input_kind: str,
        held_frames: int,
        *,
        plunge: bool,
    ) -> str:
        """左键点按/长按双语义：长按改判重击，点按保持普攻。

        重击不是独立按键——游戏内由左键按住后释放触发，故物理键只映射普攻，
        重击在此按按住时长派生。空中左键为下落攻击（``plunge``），不再进入
        分界判定。未声明重击动作的角色（``hold_input_min_frames`` 缺省）不做
        双语义改判。
        """

        min_frames = self._spec.hold_input_min_frames
        if min_frames is None or plunge or input_kind != NORMAL_ATTACK_INPUT:
            return input_kind
        if held_frames >= min_frames:
            return CHARGED_ATTACK_INPUT
        return input_kind

    def _is_airborne_plunge(self, last_action_key: str, height: float) -> bool:
        """空中左键改判下落攻击；已在下落中不重复起手，回落由同一次下落承载。"""

        return height >= PLUNGE_LOW_AIR_HEIGHT and last_action_key != self._spec.plunge_action_key

    # --- 选择 ---------------------------------------------------------------------

    def _select_action(
        self,
        context: ActionInterpretationContext,
        *,
        slot: int,
        frame: int,
        held_frames: int,
        input_kind: str,
        last_action_key: str,
        last_action_start_frame: int,
        height: float,
    ) -> TimedActionSpec:
        overridden = self._select_action_override(
            context,
            slot=slot,
            frame=frame,
            held_frames=held_frames,
            input_kind=input_kind,
            last_action_key=last_action_key,
            height=height,
        )
        if overridden is not None:
            return overridden
        if input_kind == NORMAL_ATTACK_INPUT:
            if self._is_airborne_plunge(last_action_key, height):
                return self._action_table[self._spec.plunge_action_key]
            return self._select_normal_attack_action(
                last_action_key,
                last_action_start_frame,
                frame,
            )
        if input_kind == CHARGED_ATTACK_INPUT:
            if self._spec.charged_attack_action_key is None:
                raise GenericCharacterActionError(
                    f"{self._spec.display_name}未声明重击动作，输入种类 {input_kind} 不可达"
                )
            return self._action_table[self._spec.charged_attack_action_key]
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[self._spec.elemental_skill_action_key]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[self._spec.elemental_burst_action_key]
        if input_kind == JUMP_INPUT:
            if self._spec.jump_action_key is None:
                raise GenericCharacterActionError(
                    f"{self._spec.display_name}未声明跳跃动作，输入种类 {input_kind} 不可达"
                )
            return self._action_table[self._spec.jump_action_key]
        msg = f"未知{self._spec.display_name}输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(
        self,
        last_action_key: str,
        last_action_start_frame: int,
        frame: int,
    ) -> TimedActionSpec:
        """普攻连段推进：连段窗口是上一动作自身时长（含结束帧）。

        窗口内按普攻推进到下一段（末段回绕第一段）；上一动作不属于连段序列
        （重击/战技/爆发/跳跃/下落之后）或窗口已过，回第一段。边界含结束帧：
        现有普攻行「接下一普攻」的衔接帧普遍等于时长，若按排他边界，缓冲重评
        恰好在结束帧到达时会被判过期，现有数据将无法连段。
        """

        keys = self._spec.normal_attack_action_keys
        if last_action_key not in keys:
            return self._action_table[keys[0]]
        last_row = self._action_table[last_action_key]
        if frame > last_action_start_frame + last_row.duration_frames:
            return self._action_table[keys[0]]
        last_index = keys.index(last_action_key)
        next_index = (last_index + 1) % len(keys)
        return self._action_table[keys[next_index]]

    # --- 环境与参数 -----------------------------------------------------------------

    def _current_height(self, context: SimulationContext) -> float:
        """空中事实以 ``player:active.position.y`` 为唯一真值。"""

        entity = self._active_entity(context)
        if entity is None:
            return 0.0
        return float(entity.position.y)

    def _active_entity(self, context: SimulationContext) -> SpatialEntity | None:
        if context.space_runtime is None:
            return None
        return context.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)

    def _action_params(
        self,
        action: TimedActionSpec,
        input_kind: str,
        height: float,
    ) -> dict[str, object]:
        params: dict[str, object] = {
            "content_handler_key": self._spec.character_handler_key,
            self._spec.action_kind_param_name: self._action_kind_value(
                action=action,
                input_kind=input_kind,
            ),
            self._spec.hit_frame_param_name: action.hit_frame,
        }
        if action.action_key != self._spec.plunge_action_key:
            return params
        params.update(
            {
                self._spec.action_kind_param_name: "plunge",
                "plunge_start_height": height,
                "plunge_variant": ("high" if height >= PLUNGE_HIGH_AIR_HEIGHT else "low"),
            }
        )
        return params


def compile_character_actions(
    spec: GenericCharacterActionSpec,
    *,
    cooldown_duration_terms: Mapping[str, tuple[CooldownDurationTerm, ...]] | None = None,
) -> tuple[Action, ...]:
    """把角色动作表编译为可注册的定时动作。

    ``cooldown_duration_terms`` 按能力键挂到对应定时动作上；下落动作替换为
    ``FallPlungeAction``；没有对应定时动作的能力键在此确定性失败。
    """

    terms_by_ability = dict(cooldown_duration_terms or {})
    actions: list[Action] = list(build_timed_actions(tuple(spec.action_table.values())))
    cooldown_abilities = {
        action.cooldown_ability_key
        for action in actions
        if isinstance(action, TimedImpactAction) and action.cooldown_ability_key is not None
    }
    unmatched = set(terms_by_ability) - cooldown_abilities
    if unmatched:
        keys = ", ".join(sorted(unmatched))
        raise ValueError(f"冷却时长 term 没有对应的定时动作冷却能力：{keys}")
    for index, action in enumerate(actions):
        if action.action_key == spec.plunge_action_key:
            actions[index] = FallPlungeAction(
                action_key=spec.plunge_action_key,
                collision_impact_key=spec.plunge_collision_impact_key,
                landing_impact_key=spec.plunge_landing_impact_key,
            )
            continue
        if not isinstance(action, TimedImpactAction):
            continue
        ability_key = action.cooldown_ability_key
        if ability_key is None or ability_key not in terms_by_ability:
            continue
        actions[index] = replace(
            action,
            cooldown_duration_terms=terms_by_ability[ability_key],
        )
    return tuple(actions)
