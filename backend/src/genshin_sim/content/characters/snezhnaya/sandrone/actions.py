"""桑多涅动作解释器：角色唯一动作表 + 唯一动作解释器。

桑多涅的全部已接入动作（普攻三段、元素战技、元素爆发、跳跃）统一声明在
``data.py`` 的 ``SANDRONE_ACTION_TABLE``，由本解释器独占消费；普攻推进与
跨输入衔接按表内 transitions 实现。左键为点按/长按双语义输入：按下即按
重击蓄力处理——无动作实例与伤害命中点，按下/松开按法洁欧状态机分派
``state_patch``（待机切入解算、解算幂等吸收、过载恢复射击）；前摇 36F 内
松开改判点按普攻（清蓄力状态，普攻从松开帧起手），前摇完成后松开退出
解算/停火；右键（冲刺）未接入。元素战技施放即触发解算功率快速排空。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
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
    INPUT_KIND_BY_KEY,
    JUMP_INPUT,
    NORMAL_ATTACK_INPUT,
    SANDRONE_ACTION_TABLE,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
    SANDRONE_JUMP_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_ACTION_KEYS,
    SANDRONE_P4_PRISM2_BOOST_PARAM,
    SANDRONE_P4_TACTICS_STACKS_PARAM,
    SANDRONE_PLUNGE_ACTION_KEY,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
    SANDRONE_TACTICS_CONSUME_IMPACT_KEY,
    SandroneP4AssetValues,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import radiance_evidence
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
from genshin_sim.content.generic.transitions import (
    TransitionVerdict,
    evaluate_transition,
)
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
    FallPlungeAction,
    InputSessionView,
    PreparedAction,
    TimedImpactAction,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.json import JSONValue
from genshin_sim.core.contracts.phases import FramePhase
from genshin_sim.core.coordination.character_ability_condition.models import (
    CharacterAbilityConditionQuery,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.space.entities import SpatialEntity
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.buff.models import BuffInstanceRef, BuffRecord
from genshin_sim.core.systems.buff.protocols import BuffReader
from genshin_sim.core.systems.cooldown import CooldownDurationTerm


class SandroneInterpreterError(RuntimeError):
    """桑多涅解释器运行期错误（接线缺失或状态不一致）。"""


class SandroneActionInterpreter:
    """按已确认帧表解释桑多涅动作输入。"""

    def __init__(
        self,
        *,
        action_table: dict[str, TimedActionSpec] | None = None,
        p4: SandroneP4AssetValues | None = None,
        tactics_definition_key: str | None = None,
    ) -> None:
        self._action_table = dict(action_table or SANDRONE_ACTION_TABLE)
        # P4 数值取自资产效果行（content.py 装配期传入）；突破 1 阶前为 None，
        # 相关行为（棱晶弹强化、爆发清层与光束加成）不触发。
        self._p4 = p4
        if (p4 is None) != (tactics_definition_key is None):
            raise SandroneInterpreterError("P4 数值与改进战术 Buff 定义键必须同时提供或同时缺省")
        self._tactics_definition_key = tactics_definition_key

    @property
    def supported_action_keys(self) -> tuple[str, ...]:
        return tuple(self._action_table)

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        input_kind = INPUT_KIND_BY_KEY.get(session.key)
        if input_kind == NORMAL_ATTACK_INPUT and session.owner.slot is not None:
            # 左键点按/长按双语义在按下/松开触发器上均需分派，先于其他输入
            # 的 PRESS 等待；返回 None 表示点按改判，落入下方普攻松开路径。
            attack_result = self._interpret_attack_input(
                context,
                session,
                session.owner.slot,
            )
            if attack_result is not None:
                return attack_result
        if session.trigger is ActionInterpretationTrigger.PRESS:
            return ActionInterpretationResult.wait()
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        if session.release_frame is None:
            return ActionInterpretationResult.reject("缺少释放帧")

        if input_kind is None:
            return ActionInterpretationResult.reject(f"桑多涅不支持输入：{session.key}")
        if session.owner.slot is None:
            return ActionInterpretationResult.reject("桑多涅动作需要角色归属槽位")

        slot = session.owner.slot
        height = self._current_height(context.simulation)
        last_action_key, last_action_start_frame = self._read_state(
            context.simulation,
            slot,
        )
        self._validate_known_state(last_action_key)
        if last_action_key == SANDRONE_PLUNGE_ACTION_KEY and height <= 0:
            last_action_key = ""

        if input_kind == ELEMENTAL_SKILL_INPUT:
            rejection = self._elemental_skill_rejection(
                context,
                slot,
                session.current_frame,
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)
        if input_kind == ELEMENTAL_BURST_INPUT:
            rejection = self._elemental_burst_rejection(
                context,
                slot,
                session.current_frame,
            )
            if rejection is not None:
                return ActionInterpretationResult.reject(rejection)

        # 衔接判定用当前解释帧（重评路径即为重评帧）：未到最早衔接帧由解释器
        # 交管理器缓冲，查无衔接数据仍为终局拒绝。
        verdict = self._transition_verdict(
            input_kind,
            session.current_frame,
            last_action_key,
            last_action_start_frame,
        )
        if verdict.before_earliest:
            return ActionInterpretationResult.defer(verdict.reject_message())
        if verdict.missing_data:
            return ActionInterpretationResult.reject(verdict.reject_message())

        action = self._select_action(input_kind, last_action_key, height)
        owner_ref = f"character:slot_{slot}"
        prism2_boost = False
        tactics_stacks = 0
        if input_kind == ELEMENTAL_SKILL_INPUT:
            # 判定在施放帧完成一次，结果随 E 动作参数透传给第二枚棱晶弹的
            # 影响点（不再写跨帧状态字段、也不需要时间窗口）。
            prism2_boost = self._queue_e_drain_patch(
                context.simulation,
                owner_ref=owner_ref,
                frame=session.current_frame,
                session_id=session.session_id,
            )
        if input_kind == ELEMENTAL_BURST_INPUT and self._p4 is not None:
            # P4 光束加成：施放帧消费改进战术，只取出层数
            # 随 Q 动作参数透传给聚能光束影响点；
            tactics_stacks = self._consume_tactics_stacks(
                context,
                owner_ref=owner_ref,
                frame=session.current_frame,
                session_id=session.session_id,
            )
        self._queue_state_patch(
            context.simulation,
            owner_ref=owner_ref,
            frame=session.current_frame,
            session_id=session.session_id,
            action=action,
            start_frame=session.current_frame,
        )
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key=action.action_key,
                owner=ActionOwnerRef.character(slot),
                requested_start_frame=session.current_frame,
                params=self._action_params(
                    action,
                    input_kind,
                    height,
                    prism2_boost=prism2_boost,
                    tactics_stacks=tactics_stacks,
                ),
                source_session_id=session.session_id,
            )
        )

    def _elemental_skill_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
    ) -> str | None:
        """公共条件端口未接线时不阻断，真实装配必须提供端口。"""

        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key="elemental_skill",
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "桑多涅元素战技冷却未就绪"

    def _elemental_burst_rejection(
        self,
        context: ActionInterpretationContext,
        slot: int,
        frame: int,
    ) -> str | None:
        """公共条件端口未接线时不阻断，真实装配必须提供端口。"""

        port = context.ability_condition_port
        if port is None:
            return None
        result = port.evaluate(
            CharacterAbilityConditionQuery(
                frame=frame,
                character_id=f"character:slot_{slot}",
                ability_key="elemental_burst",
            )
        )
        if result.shared_conditions_satisfied:
            return None
        return "桑多涅元素爆发冷却或能量未就绪"

    def _read_state(
        self,
        context: SimulationContext,
        slot: int,
    ) -> tuple[str, int]:
        try:
            mount = resolve_mount(
                context,
                slot=slot,
                state_key=SANDRONE_CHARACTER_HANDLER_KEY,
            )
        except StateContainerNotFoundError as exc:
            raise SandroneInterpreterError(f"缺少桑多涅状态挂载：{exc}") from exc
        raw_key = mount.values.get(CHAIN_STATE_LAST_ACTION_KEY)
        last_key = raw_key if isinstance(raw_key, str) else ""
        raw_start = mount.values.get(CHAIN_STATE_LAST_START_FRAME)
        last_start = (
            raw_start if isinstance(raw_start, int) and not isinstance(raw_start, bool) else 0
        )
        return last_key, last_start

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
        *,
        prism2_boost: bool = False,
        tactics_stacks: int = 0,
    ) -> dict[str, object]:
        params: dict[str, object] = {
            "content_handler_key": SANDRONE_CHARACTER_HANDLER_KEY,
            "sandrone_action_kind": input_kind,
            "sandrone_hit_frame": action.hit_frame,
        }
        if action.action_key == SANDRONE_ELEMENTAL_SKILL_ACTION_KEY:
            # P4 棱晶弹强化标记：E 动作的两个影响点都携带，影响工厂只对
            # 第二枚棱晶弹消费（键值常量见 data.py）。
            params[SANDRONE_P4_PRISM2_BOOST_PARAM] = prism2_boost
        if action.action_key == SANDRONE_ELEMENTAL_BURST_ACTION_KEY:
            # P4 改进战术消费层数：Q 施放帧读到多少层就带多少层（未消费为 0），
            # 影响工厂只对聚能光束影响点消费（键值常量见 data.py）。
            params[SANDRONE_P4_TACTICS_STACKS_PARAM] = tactics_stacks
        if action.action_key != SANDRONE_PLUNGE_ACTION_KEY:
            return params
        params.update(
            {
                "sandrone_action_kind": "plunge",
                "plunge_start_height": height,
                "plunge_variant": ("high" if height >= PLUNGE_HIGH_AIR_HEIGHT else "low"),
            }
        )
        return params

    def _validate_known_state(self, last_action_key: str) -> None:
        """状态损坏时确定性报错，不允许静默重启。"""

        if last_action_key and last_action_key not in self._action_table:
            raise SandroneInterpreterError(f"未知桑多涅动作状态：{last_action_key}")

    def _queue_state_patch(
        self,
        context: SimulationContext,
        *,
        owner_ref: str,
        frame: int,
        session_id: int,
        action: TimedActionSpec,
        start_frame: int,
    ) -> None:
        queue = cast(IntentQueue | None, context.get_system(IntentQueue))
        if queue is None:
            raise SandroneInterpreterError("缺少 IntentQueue，无法提交桑多涅状态")
        queue.enqueue(
            IntentEnvelope(
                intent_id=f"sandrone_state:{owner_ref}:{session_id}:{frame}",
                kind=IntentKind.STATE_PATCH,
                frame=frame,
                phase=FramePhase.SETTLEMENT,
                round=context.settlement_round + 1,
                source_ref=SANDRONE_CHARACTER_HANDLER_KEY,
                payload=StatePatchRequest(
                    owner_ref=owner_ref,
                    state_key=SANDRONE_CHARACTER_HANDLER_KEY,
                    fields={
                        CHAIN_STATE_LAST_ACTION_KEY: action.action_key,
                        CHAIN_STATE_LAST_START_FRAME: start_frame,
                    },
                ),
            )
        )

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

    def _interpret_attack_input(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
        slot: int,
    ) -> ActionInterpretationResult | None:
        """左键点按/长按双语义。

        按下即按重击蓄力处理：待机切入解算（前摇 36F 后开始射击与功率
        上升）；解算态按下幂等吸收（不重置会话状态）；过载态功率 ≥50
        按下恢复射击。长按（HOLD）等待。松开按前摇边界改判：按住不足
        前摇 36F 视为点按——清除本次按下写入的蓄力状态并返回 None，由
        普攻松开路径从松开帧起手；按住达到前摇按重击松开处理（退出
        解算；过载停火但模式保持）。重击本身无动作实例与伤害命中点。
        """

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

    def _transition_verdict(
        self,
        input_kind: str,
        frame: int,
        last_action_key: str,
        last_action_start_frame: int,
    ) -> TransitionVerdict:
        """按桑多涅动作表判定衔接三态（共享 generic 判定）。"""

        return evaluate_transition(
            action_table=self._action_table,
            display_name="桑多涅",
            prev_action_key=last_action_key,
            input_kind=input_kind,
            frame=frame,
            prev_start_frame=last_action_start_frame,
        )

    def _select_action(
        self,
        input_kind: str,
        last_action_key: str,
        height: float,
    ) -> TimedActionSpec:
        if input_kind == NORMAL_ATTACK_INPUT:
            if height >= PLUNGE_LOW_AIR_HEIGHT and last_action_key != SANDRONE_PLUNGE_ACTION_KEY:
                return self._action_table[SANDRONE_PLUNGE_ACTION_KEY]
            return self._select_normal_attack_action(last_action_key)
        if input_kind == ELEMENTAL_SKILL_INPUT:
            return self._action_table[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY]
        if input_kind == ELEMENTAL_BURST_INPUT:
            return self._action_table[SANDRONE_ELEMENTAL_BURST_ACTION_KEY]
        if input_kind == JUMP_INPUT:
            return self._action_table[SANDRONE_JUMP_ACTION_KEY]
        msg = f"未知桑多涅输入类型：{input_kind}"
        raise KeyError(msg)

    def _select_normal_attack_action(self, last_action_key: str) -> TimedActionSpec:
        if last_action_key not in SANDRONE_NORMAL_ATTACK_ACTION_KEYS:
            return self._action_table[SANDRONE_NORMAL_ATTACK_ACTION_KEYS[0]]
        last_index = SANDRONE_NORMAL_ATTACK_ACTION_KEYS.index(last_action_key)
        next_index = (last_index + 1) % len(SANDRONE_NORMAL_ATTACK_ACTION_KEYS)
        return self._action_table[SANDRONE_NORMAL_ATTACK_ACTION_KEYS[next_index]]


def create_sandrone_actions(
    action_table: dict[str, TimedActionSpec] | None = None,
    *,
    cooldown_duration_terms: (Mapping[str, tuple[CooldownDurationTerm, ...]] | None) = None,
) -> tuple[Action, ...]:
    """把角色唯一动作表编译为可注册的定时动作。"""

    table = dict(action_table or SANDRONE_ACTION_TABLE)
    terms_by_ability = dict(cooldown_duration_terms or {})
    actions: list[Action] = list(build_timed_actions(tuple(table.values())))
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
        if action.action_key == SANDRONE_PLUNGE_ACTION_KEY:
            actions[index] = FallPlungeAction(
                action_key=SANDRONE_PLUNGE_ACTION_KEY,
                collision_impact_key=SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
                landing_impact_key=SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
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
