"""桑多涅动作解释挂点：动作解释由 generic 通用解释器承担。

桑多涅的角色差异有两处，分别经命名挂点接入，其余行为全部由
``data.SANDRONE_ACTION_SPEC`` 数据面承载：

- 左键法洁欧蓄力状态机（``_input_override``）：按下即按重击处理——
  待机切入解算（前摇 36F 后开始射击与功率上升）、解算态按下幂等吸收、
  过载态功率达标恢复射击；前摇 36F 内松开改判点按普攻（清除本次按下写入
  的蓄力状态，普攻从松开帧起手），前摇完成后松开退出解算/停火。重击本身
  无动作实例与伤害命中点。
- E/Q 施放帧效果（``_cast_frame_effects``）：E 排空（施放即退出解算/过载
  并快速排空功率）并判定 P4 棱晶弹强化；Q 消费改进战术并把层数随动作参数
  透传给聚能光束影响点。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    ELEMENTAL_BURST_INPUT,
    ELEMENTAL_SKILL_INPUT,
    FAGEOU_MODE_IDLE,
    FAGEOU_MODE_OVERLOAD,
    FAGEOU_MODE_SOLVE,
    FAGEOU_OVERLOAD_EXIT_POWER,
    FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
    FAGEOU_PRE_SWING_FRAMES,
    FAGEOU_RAY_FIRST_OFFSET_FRAMES,
    FAGEOU_STATE_DRAIN_ACTIVE,
    FAGEOU_STATE_EXTRA_SEGMENTS_LEFT,
    FAGEOU_STATE_MODE,
    FAGEOU_STATE_NEXT_RAY_FRAME,
    FAGEOU_STATE_NEXT_SHOT_FRAME,
    FAGEOU_STATE_POWER,
    FAGEOU_STATE_RAY_COUNT,
    FAGEOU_STATE_SOLVE_START_FRAME,
    NORMAL_ATTACK_INPUT,
    SANDRONE_ACTION_SPEC,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_P4_PRISM2_BOOST_PARAM,
    SANDRONE_P4_TACTICS_STACKS_PARAM,
    SANDRONE_TACTICS_CONSUME_IMPACT_KEY,
    SandroneP4AssetValues,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import radiance_evidence
from genshin_sim.content.generic.character_actions import (
    GenericCharacterActionInterpreter,
)
from genshin_sim.content.generic.timed_action import TimedActionSpec
from genshin_sim.content.state_container import (
    StateContainerNotFoundError,
    StatePatchRequest,
    resolve_mount,
)
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    InputSessionView,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.systems.buff.models import BuffInstanceRef, BuffRecord
from genshin_sim.core.systems.buff.protocols import BuffReader


class SandroneInterpreterError(RuntimeError):
    """桑多涅解释器运行期错误（接线缺失或状态不一致）。"""


class SandroneActionInterpreter(GenericCharacterActionInterpreter):
    """桑多涅动作解释器：generic 骨架 + 法洁欧状态机与施放帧效果挂点。"""

    def __init__(
        self,
        *,
        action_table: Mapping[str, TimedActionSpec] | None = None,
        p4: SandroneP4AssetValues | None = None,
        tactics_definition_key: str | None = None,
    ) -> None:
        super().__init__(SANDRONE_ACTION_SPEC, action_table=action_table)
        # P4 数值取自资产效果行（content.py 装配期传入）；突破 1 阶前为 None，
        # 相关行为（棱晶弹强化、爆发清层与光束加成）不触发。
        self._p4 = p4
        if (p4 is None) != (tactics_definition_key is None):
            raise SandroneInterpreterError("P4 数值与改进战术 Buff 定义键必须同时提供或同时缺省")
        self._tactics_definition_key = tactics_definition_key

    # --- 挂点：左键蓄力状态机 -------------------------------------------------------

    def _input_override(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
        input_kind: str,
    ) -> ActionInterpretationResult | None:
        if input_kind != NORMAL_ATTACK_INPUT:
            return None
        return self._interpret_attack_input(context, session, slot)

    def _interpret_attack_input(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
    ) -> ActionInterpretationResult | None:
        """左键点按/长按双语义（法洁欧状态机分派），见模块 docstring。"""

        frame = session.current_frame
        fields: dict[str, JSONValue] | None
        if session.trigger is ActionInterpretationTrigger.PRESS:
            mode, power = self._read_fageou_state(context.simulation, slot)
            fields = self._charged_press_fields(mode, power, frame)
        elif session.trigger is ActionInterpretationTrigger.RELEASE:
            if session.release_frame is None:
                return ActionInterpretationResult.reject("缺少释放帧")
            mode, _power = self._read_fageou_state(context.simulation, slot)
            fields = self._charged_release_fields(mode)
            if session.held_frames < FAGEOU_PRE_SWING_FRAMES:
                # 点按改判：清除本次按下写入的蓄力状态，普攻由通用松开路径
                # 从松开帧起手。
                if fields is not None:
                    self._queue_machine_patch(
                        context.simulation,
                        owner_ref=f"character:slot_{slot}",
                        frame=frame,
                        session_id=session.session_id,
                        fields=fields,
                    )
                return None
        else:
            fields = None
        if fields is not None:
            self._queue_machine_patch(
                context.simulation,
                owner_ref=f"character:slot_{slot}",
                frame=frame,
                session_id=session.session_id,
                fields=fields,
            )
        return ActionInterpretationResult.wait()

    # --- 挂点：施放帧效果 -----------------------------------------------------------

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
        if input_kind == ELEMENTAL_SKILL_INPUT:
            # 判定在施放帧完成一次，结果随 E 动作参数透传给第二枚棱晶弹的
            # 影响点（不写跨帧状态字段、也不需要时间窗口）。
            prism2_boost = self._queue_e_drain_patch(
                context.simulation,
                owner_ref=owner_ref,
                frame=frame,
                session_id=session_id,
            )
            return {SANDRONE_P4_PRISM2_BOOST_PARAM: prism2_boost}
        if input_kind == ELEMENTAL_BURST_INPUT and self._p4 is not None:
            # P4 光束加成：施放帧消费改进战术，层数随 Q 动作参数透传。
            tactics_stacks = self._consume_tactics_stacks(
                context,
                owner_ref=owner_ref,
                frame=frame,
                session_id=session_id,
            )
            return {SANDRONE_P4_TACTICS_STACKS_PARAM: tactics_stacks}
        return {}

    # --- 法洁欧状态机 -----------------------------------------------------------------

    def _read_fageou_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, float]:
        """读取法洁欧模式机的当前模式与解算功率。"""

        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SANDRONE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SandroneInterpreterError(f"缺少桑多涅状态挂载：{exc}") from exc
        raw_mode = mount.values.get(FAGEOU_STATE_MODE)
        mode = raw_mode if isinstance(raw_mode, str) else FAGEOU_MODE_IDLE
        raw_power = mount.values.get(FAGEOU_STATE_POWER)
        power = (
            float(raw_power)
            if isinstance(raw_power, int | float) and not isinstance(raw_power, bool)
            else 0.0
        )
        return mode, power

    def _charged_press_fields(
        self,
        mode: str,
        power: float,
        frame: int,
    ) -> dict[str, JSONValue] | None:
        if mode == FAGEOU_MODE_SOLVE:
            return None
        if mode == FAGEOU_MODE_OVERLOAD and power >= FAGEOU_OVERLOAD_EXIT_POWER:
            # 功率 ≥50 期间重新按住：恢复过载射击节奏。
            return {
                FAGEOU_STATE_NEXT_SHOT_FRAME: frame + FAGEOU_OVERLOAD_SHOT_INTERVAL_FRAMES,
            }
        solve_start = frame + FAGEOU_PRE_SWING_FRAMES
        return {
            FAGEOU_STATE_MODE: FAGEOU_MODE_SOLVE,
            FAGEOU_STATE_SOLVE_START_FRAME: solve_start,
            FAGEOU_STATE_NEXT_SHOT_FRAME: solve_start,
            # 射线首发自按下起算（前摇 36F 期间不发射子弹，见 data.py 节奏注释）。
            FAGEOU_STATE_NEXT_RAY_FRAME: frame + FAGEOU_RAY_FIRST_OFFSET_FRAMES,
            # 射线会话序号与 C6 追加段余量按重击会话重置（C2 每轮重击重新
            # 叠层；C6 的「第 3 次发射起」判定随新会话重新计数）。
            FAGEOU_STATE_RAY_COUNT: 0,
            FAGEOU_STATE_EXTRA_SEGMENTS_LEFT: 0,
        }

    def _charged_release_fields(self, mode: str) -> dict[str, JSONValue] | None:
        if mode == FAGEOU_MODE_SOLVE:
            return {
                FAGEOU_STATE_MODE: FAGEOU_MODE_IDLE,
                FAGEOU_STATE_SOLVE_START_FRAME: 0,
                FAGEOU_STATE_NEXT_SHOT_FRAME: 0,
                FAGEOU_STATE_NEXT_RAY_FRAME: 0,
            }
        if mode == FAGEOU_MODE_OVERLOAD:
            return {FAGEOU_STATE_NEXT_SHOT_FRAME: 0}
        return None

    def _queue_machine_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        fields: dict[str, JSONValue],
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise SandroneInterpreterError("缺少 IntentQueue，无法提交法洁欧状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sandrone_fageou:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=SANDRONE_CHARACTER_HANDLER_KEY,
                    fields=fields,
                ),
            )
        )

    # --- 施放帧效果 -----------------------------------------------------------------

    def _queue_e_drain_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
    ) -> bool:
        """E 排空：施放即退出解算/过载并快速排空功率。

        P4 强化条件在施放帧判定一次，读取的是功率清空前的取值（排空是跨帧
        推进的）：解算功率超过阈值且施放时持有辉映状态时，返回 ``True``，
        由调用方写入 E 动作参数交给第二枚棱晶弹影响点消费；P4 未解锁
        （突破 1 阶前）或条件不命中时返回 ``False``。本方法不再写状态字段。
        """

        slot = int(owner_ref.removeprefix("character:slot_"))
        mode, power = self._read_fageou_state(context, slot)
        p4 = self._p4
        prism2_boost = (
            p4 is not None
            and power > p4.power_threshold
            and radiance_evidence(context, owner_ref, frame) is not None
        )
        if mode == FAGEOU_MODE_IDLE and power <= 0.0:
            return prism2_boost
        fields: dict[str, JSONValue] = {
            FAGEOU_STATE_MODE: FAGEOU_MODE_IDLE,
            FAGEOU_STATE_SOLVE_START_FRAME: 0,
            FAGEOU_STATE_NEXT_SHOT_FRAME: 0,
            FAGEOU_STATE_NEXT_RAY_FRAME: 0,
            FAGEOU_STATE_DRAIN_ACTIVE: True,
        }
        self._queue_machine_patch(
            context,
            owner_ref=owner_ref,
            frame=frame,
            session_id=session_id,
            fields=fields,
        )
        return prism2_boost

    def _consume_tactics_stacks(
        self,
        context: ActionInterpretationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
    ) -> int:
        """辉映下施放爆发：消费改进战术并返回被清除的层数（P4）。"""

        if self._p4 is None or self._tactics_definition_key is None:
            raise SandroneInterpreterError("P4 未解锁时不应消费改进战术")
        if context.buff_reader is None:
            raise SandroneInterpreterError(
                "缺少 Buff 只读端口（装配期未注入动作管理器），无法消费改进战术"
            )
        if radiance_evidence(context.simulation, owner_ref, frame) is None:
            return 0
        record = self._active_tactics_record(
            context.buff_reader,
            owner_ref=owner_ref,
            frame=frame,
        )
        if record is None:
            return 0
        stacks = record.state.stack_count
        self._queue_tactics_removal(
            context.simulation,
            owner_ref=owner_ref,
            frame=frame,
            session_id=session_id,
            instance_ref=record.instance_ref,
        )
        return stacks

    def _active_tactics_record(
        self,
        buff_reader: BuffReader,
        *,
        owner_ref: str,
        frame: int,
    ) -> BuffRecord | None:
        """读取宿主当前活动的改进战术记录；冲突键保证至多一条。"""

        if self._tactics_definition_key is None:  # pragma: no cover - 构造期已校验
            raise SandroneInterpreterError("缺少改进战术 Buff 定义键")
        records = buff_reader.active(
            frame,
            target_ref=AttributeSubjectRef.character(owner_ref),
            definition_key=self._tactics_definition_key,
        )
        if not records:
            return None
        first, *rest = records
        if rest:
            raise SandroneInterpreterError(
                f"改进战术 Buff 出现多条活动记录：{len(records)} 条（冲突键应保证互斥）"
            )
        return first

    def _queue_tactics_removal(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        instance_ref: BuffInstanceRef,
    ) -> None:
        """以 REMOVE_STATUS 影响请求提交改进战术消费移除。

        消费方读记录、移除 handler 不推断（buff/handler.py 契约）：实例身份
        由本方法携带；移除经意图队列在下一轮结算落地。
        """

        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise SandroneInterpreterError("缺少 IntentQueue，无法提交改进战术消费移除")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sandrone_p4_tactics_consume:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.IMPACT,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
                payload=ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.REMOVE_STATUS,
                    impact_key=SANDRONE_TACTICS_CONSUME_IMPACT_KEY,
                    owner_slot=int(owner_ref.removeprefix("character:slot_")),
                    action_key=SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
                    source_impact_point_id=(
                        f"{SANDRONE_TACTICS_CONSUME_IMPACT_KEY}:{frame}:{session_id}"
                    ),
                    target_refs=(owner_ref,),
                    params={
                        "buff_remove": {
                            "instance_ref": instance_ref.to_key(),
                            "reason": "consumed",
                        },
                    },
                ),
            )
        )
