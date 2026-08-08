"""动作运行时：输入会话解释、动作准入、实例与影响点编排。"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from genshin_sim.core.actions.enums import (
    ActionDecisionRejectReason,
    ActionInterpretationKind,
    ActionInterpretationTrigger,
    ActionLifecycle,
    ActionLifecycleDirective,
    InputControlState,
    InputPhysicalState,
    InputSessionPolicy,
)
from genshin_sim.core.actions.interpreters import ActionInterpreterRegistry
from genshin_sim.core.actions.models import (
    ActionAdmissionPolicy,
    ActionDecision,
    ActionExecutionContext,
    ActionExecutionRecord,
    ActionExecutionResult,
    ActionImpactPoint,
    ActionInstance,
    ActionInterpretationResult,
    ActionOwnerRef,
    ControlActionRequest,
    InputSessionView,
    PreparedAction,
    RuntimeInputSession,
)
from genshin_sim.core.actions.protocols import ActionRegistry
from genshin_sim.core.events import (
    EventType,
    GameEvent,
    InputKeyReceivedPayload,
    InputSessionBoundaryPayload,
)
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.input import InputSessionBoundary, InputSessionTrace, KeyPhase

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


class ActionManager(FrameUpdatable):
    """输入会话解释、动作准入、动作实例和影响点的统一运行时入口。"""

    def __init__(
        self,
        *,
        input_trace: InputSessionTrace,
        interpreter_registry: ActionInterpreterRegistry,
        action_registry: ActionRegistry,
    ) -> None:
        self.input_trace = input_trace
        self.interpreter_registry = interpreter_registry
        self.action_registry = action_registry
        self._sessions: dict[int, RuntimeInputSession] = {}
        self._instances: list[ActionInstance] = []
        self._decisions: list[ActionDecision] = []
        self._execution_records: list[ActionExecutionRecord] = []
        self._current_frame = 0
        self._next_instance_id = 1
        self._next_request_id = 1
        self._started_this_frame: set[int] = set()

    @property
    def sessions(self) -> tuple[RuntimeInputSession, ...]:
        return tuple(sorted(self._sessions.values(), key=lambda item: item.session_id))

    @property
    def instances(self) -> tuple[ActionInstance, ...]:
        return tuple(self._instances)

    @property
    def decisions(self) -> tuple[ActionDecision, ...]:
        return tuple(self._decisions)

    @property
    def execution_records(self) -> tuple[ActionExecutionRecord, ...]:
        return tuple(self._execution_records)

    @property
    def active_instances(self) -> tuple[ActionInstance, ...]:
        return tuple(
            instance
            for instance in self._instances
            if instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
        )

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        if frame < 0:
            msg = "帧号不能为负数"
            raise ValueError(msg)
        self._current_frame = frame
        self._started_this_frame = set()
        self._start_due_instances(context, frame)
        released_sessions: set[int] = set()
        pressed_sessions: set[int] = set()
        for boundary in self.input_trace.boundaries_at(frame):
            self._publish_input_key_received(context, boundary)
            if boundary.phase is KeyPhase.PRESS:
                pressed_sessions.add(boundary.session_id)
                self._handle_press(context, boundary, frame)
                continue
            released_sessions.add(boundary.session_id)
            self._handle_release(context, boundary, frame)
        self._handle_holds(context, frame, pressed_sessions | released_sessions)
        self._update_running_instances(context, frame)

    def is_idle(self) -> bool:
        if self.input_trace.has_pending_after(self._current_frame):
            return False
        if any(
            session.physical_state is InputPhysicalState.HELD
            or session.control_state is InputControlState.LISTENING
            for session in self._sessions.values()
        ):
            return False
        if any(
            instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
            for instance in self._instances
        ):
            return False
        return not any(point.status == "pending" for point in self.iter_impact_points())

    def iter_impact_points(self) -> tuple[ActionImpactPoint, ...]:
        return tuple(point for instance in self._instances for point in instance.impact_points)

    def due_impact_points(self, frame: int) -> tuple[ActionImpactPoint, ...]:
        return tuple(
            point
            for point in self.iter_impact_points()
            if point.status == "pending" and point.scheduled_frame <= frame
        )

    def mark_impact_dispatched(self, impact_point_id: str) -> None:
        for instance in self._instances:
            for index, point in enumerate(instance.impact_points):
                if point.impact_point_id != impact_point_id:
                    continue
                instance.impact_points[index] = replace(point, status="dispatched")
                return
        msg = f"未知影响点：{impact_point_id}"
        raise KeyError(msg)

    def _handle_press(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
        frame: int,
    ) -> None:
        plan = self.input_trace.get_session(boundary.session_id)
        binding = self.interpreter_registry.resolve(plan.key, context)
        session = RuntimeInputSession(
            session_id=plan.session_id,
            key=plan.key,
            press_frame=plan.press_frame,
            physical_state=InputPhysicalState.HELD,
            control_state=InputControlState.LISTENING,
            interpreter_binding=binding,
            owner=binding.owner,
        )
        self._sessions[boundary.session_id] = session
        self._publish_input_session_boundary(
            context,
            session,
            boundary,
            will_interpret=True,
            skip_reason=None,
        )
        self._interpret(context, session, ActionInterpretationTrigger.PRESS, frame)

    def _handle_release(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
        frame: int,
    ) -> None:
        session = self._sessions[boundary.session_id]
        session.physical_state = InputPhysicalState.RELEASED
        session.released_frame = frame
        will_interpret = session.control_state is InputControlState.LISTENING
        self._publish_input_session_boundary(
            context,
            session,
            boundary,
            will_interpret=will_interpret,
            skip_reason=None if will_interpret else session.control_state.value,
        )
        if will_interpret:
            self._interpret(context, session, ActionInterpretationTrigger.RELEASE, frame)
        if session.control_state is InputControlState.LISTENING:
            session.control_state = InputControlState.DETACHED

    def _publish_input_key_received(
        self,
        context: SimulationContext,
        boundary: InputSessionBoundary,
    ) -> None:
        plan = self.input_trace.get_session(boundary.session_id)
        context.events.publish(
            GameEvent(
                EventType.INPUT_KEY_RECEIVED,
                frame=boundary.frame,
                source=self,
                payload=InputKeyReceivedPayload(
                    key=plan.key,
                    phase=boundary.phase.value,
                    order=boundary.order,
                    session_id=boundary.session_id,
                ),
            )
        )

    def _publish_input_session_boundary(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        boundary: InputSessionBoundary,
        *,
        will_interpret: bool,
        skip_reason: str | None,
    ) -> None:
        context.events.publish(
            GameEvent(
                EventType.INPUT_SESSION_BOUNDARY_REACHED,
                frame=boundary.frame,
                source=self,
                payload=InputSessionBoundaryPayload(
                    session_id=session.session_id,
                    key=session.key,
                    phase=boundary.phase.value,
                    order=boundary.order,
                    press_frame=session.press_frame,
                    held_frames=boundary.frame - session.press_frame,
                    physical_state=session.physical_state.value,
                    control_state=session.control_state.value,
                    owner_kind=session.owner.kind.value,
                    owner_slot=session.owner.slot,
                    interpreter_id=session.interpreter_binding.interpreter_id,
                    binding_scope=session.interpreter_binding.scope,
                    will_interpret=will_interpret,
                    skip_reason=skip_reason,
                ),
            )
        )

    def _handle_holds(
        self,
        context: SimulationContext,
        frame: int,
        skipped_session_ids: set[int],
    ) -> None:
        for session in self.sessions:
            if session.session_id in skipped_session_ids:
                continue
            if session.physical_state is not InputPhysicalState.HELD:
                continue
            if session.control_state is not InputControlState.LISTENING:
                continue
            self._interpret(context, session, ActionInterpretationTrigger.HOLD, frame)

    def _interpret(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        trigger: ActionInterpretationTrigger,
        frame: int,
    ) -> None:
        view = self._session_view(session, trigger, frame)
        result = session.interpreter_binding.interpreter.interpret(context, view)
        self._apply_interpretation(context, session, result, frame)

    def _session_view(
        self,
        session: RuntimeInputSession,
        trigger: ActionInterpretationTrigger,
        frame: int,
    ) -> InputSessionView:
        return InputSessionView(
            session_id=session.session_id,
            key=session.key,
            trigger=trigger,
            press_frame=session.press_frame,
            current_frame=frame,
            held_frames=frame - session.press_frame,
            physical_state=session.physical_state,
            owner=session.owner,
            bound_instance=self._instance_by_id(session.bound_instance_id)
            if session.bound_instance_id is not None
            else None,
            release_frame=session.released_frame
            if trigger is ActionInterpretationTrigger.RELEASE
            else None,
        )

    def _apply_interpretation(
        self,
        context: SimulationContext,
        session: RuntimeInputSession,
        result: ActionInterpretationResult,
        frame: int,
    ) -> None:
        if result.kind is ActionInterpretationKind.WAIT:
            return
        if result.kind is ActionInterpretationKind.REJECT:
            self._apply_session_policy(session, result.session_policy, result.reason)
            return
        if result.kind is ActionInterpretationKind.START_ACTION:
            if result.prepared_action is None:
                self._apply_session_policy(session, InputSessionPolicy.DETACH, "missing_action")
                return
            decision = self._start_prepared_action(context, result.prepared_action, frame)
            if decision.accepted and result.prepared_action.bind_session_on_accept:
                session.bound_instance_id = decision.created_instance_id
            if decision.accepted or not result.prepared_action.continue_on_reject:
                self._apply_session_policy(session, result.session_policy, result.reason)
            return
        if result.control_request is None:
            self._apply_session_policy(session, InputSessionPolicy.DETACH, "missing_control")
            return
        self._control_action(context, result.control_request, frame)
        self._apply_session_policy(session, result.session_policy, result.reason)

    def _start_prepared_action(
        self,
        context: SimulationContext,
        prepared: PreparedAction,
        frame: int,
    ) -> ActionDecision:
        request_id = self._next_request_id
        self._next_request_id += 1
        if prepared.requested_start_frame < frame:
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=prepared.source_session_id,
                    accepted=False,
                    frame=frame,
                    action_key=prepared.action_key,
                    reject_reason=ActionDecisionRejectReason.INVALID_START_FRAME,
                )
            )
        if not self.action_registry.contains(prepared.action_key):
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=prepared.source_session_id,
                    accepted=False,
                    frame=frame,
                    action_key=prepared.action_key,
                    reject_reason=ActionDecisionRejectReason.UNSUPPORTED_ACTION,
                )
            )
        action = self.action_registry.get(prepared.action_key)
        conflicts = self._conflicting_instances(action.admission_policy)
        interrupted: list[int] = []
        if conflicts:
            if not all(
                self._can_interrupt(instance, prepared.interrupt_kind, frame)
                for instance in conflicts
            ):
                return self._record_decision(
                    ActionDecision(
                        request_id=request_id,
                        source_session_id=prepared.source_session_id,
                        accepted=False,
                        frame=frame,
                        action_key=prepared.action_key,
                        reject_reason=ActionDecisionRejectReason.LOCK_CONFLICT,
                    )
                )
            for instance in conflicts:
                self._cancel_instance(context, instance, frame, "interrupted")
                interrupted.append(instance.instance_id)

        instance = ActionInstance(
            instance_id=self._next_instance_id,
            action=action,
            action_key=action.action_key,
            owner=prepared.owner,
            source_session_id=prepared.source_session_id,
            created_frame=frame,
            start_frame=prepared.requested_start_frame,
            lifecycle=ActionLifecycle.SCHEDULED,
            action_state=action.create_initial_state(prepared.params),
            params=prepared.params,
        )
        self._next_instance_id += 1
        self._instances.append(instance)
        if prepared.requested_start_frame <= frame:
            self._start_instance(context, instance, frame)
        return self._record_decision(
            ActionDecision(
                request_id=request_id,
                source_session_id=prepared.source_session_id,
                accepted=True,
                frame=frame,
                action_key=prepared.action_key,
                created_instance_id=instance.instance_id,
                interrupted_instance_ids=tuple(interrupted),
            )
        )

    def _control_action(
        self,
        context: SimulationContext,
        request: ControlActionRequest,
        frame: int,
    ) -> ActionDecision:
        request_id = self._next_request_id
        self._next_request_id += 1
        instance = self._instance_by_id(request.target_instance_id)
        if instance is None:
            return self._record_decision(
                ActionDecision(
                    request_id=request_id,
                    source_session_id=None,
                    accepted=False,
                    frame=frame,
                    action_key="control",
                    reject_reason=ActionDecisionRejectReason.INSTANCE_NOT_FOUND,
                )
            )
        result = instance.action.on_command(
            self._execution_context(context, instance, frame),
            request,
        )
        self._apply_execution_result(context, instance, result, frame)
        return self._record_decision(
            ActionDecision(
                request_id=request_id,
                source_session_id=instance.source_session_id,
                accepted=True,
                frame=frame,
                action_key=instance.action_key,
                created_instance_id=instance.instance_id,
            )
        )

    def _start_due_instances(self, context: SimulationContext, frame: int) -> None:
        for instance in self._instances:
            if instance.lifecycle is ActionLifecycle.SCHEDULED and instance.start_frame <= frame:
                self._start_instance(context, instance, frame)

    def _start_instance(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
    ) -> None:
        instance.lifecycle = ActionLifecycle.RUNNING
        self._started_this_frame.add(instance.instance_id)
        result = instance.action.on_start(self._execution_context(context, instance, frame))
        self._apply_execution_result(context, instance, result, frame)

    def _update_running_instances(self, context: SimulationContext, frame: int) -> None:
        for instance in tuple(self._instances):
            if instance.lifecycle is not ActionLifecycle.RUNNING:
                continue
            if instance.instance_id in self._started_this_frame:
                continue
            result = instance.action.on_update(self._execution_context(context, instance, frame))
            self._apply_execution_result(context, instance, result, frame)

    def _apply_execution_result(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        result: ActionExecutionResult,
        frame: int,
    ) -> None:
        if result.next_state is not None:
            instance.action_state = result.next_state
        instance.impact_points.extend(result.emitted_impacts)
        for record in result.records:
            self._execution_records.append(
                ActionExecutionRecord(
                    frame=frame,
                    instance_id=instance.instance_id,
                    action_key=instance.action_key,
                    payload=record,
                )
            )
            if record.get("type") == "team_switch" and record.get("accepted") is True:
                previous_slot = record.get("previous_slot")
                if isinstance(previous_slot, int):
                    self.cancel_sessions_for_owner(
                        ActionOwnerRef.character(previous_slot),
                        reason="character_switch",
                    )
        if result.lifecycle_directive is ActionLifecycleDirective.FINISH:
            finish_result = instance.action.on_finish(
                self._execution_context(context, instance, frame)
            )
            instance.lifecycle = ActionLifecycle.COMPLETED
            instance.completed_frame = frame
            for record in finish_result.records:
                self._execution_records.append(
                    ActionExecutionRecord(
                        frame=frame,
                        instance_id=instance.instance_id,
                        action_key=instance.action_key,
                        payload=record,
                    )
                )
            return
        if result.lifecycle_directive is ActionLifecycleDirective.CANCEL:
            self._cancel_instance(context, instance, frame, result.cancel_reason or "canceled")

    def _cancel_instance(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
        reason: str,
    ) -> None:
        if instance.lifecycle in {ActionLifecycle.COMPLETED, ActionLifecycle.CANCELED}:
            return
        result = instance.action.on_cancel(
            self._execution_context(context, instance, frame),
            reason,
        )
        instance.lifecycle = ActionLifecycle.CANCELED
        instance.cancel_reason = reason
        instance.completed_frame = frame
        for index, point in enumerate(instance.impact_points):
            if point.status == "pending" and point.cancel_with_action:
                instance.impact_points[index] = replace(point, status="canceled")
        for record in result.records:
            self._execution_records.append(
                ActionExecutionRecord(
                    frame=frame,
                    instance_id=instance.instance_id,
                    action_key=instance.action_key,
                    payload=record,
                )
            )

    def cancel_sessions_for_owner(self, owner: ActionOwnerRef, *, reason: str) -> None:
        for session in self._sessions.values():
            if session.owner != owner:
                continue
            if session.control_state is not InputControlState.LISTENING:
                continue
            session.control_state = InputControlState.CANCELED
            session.cancel_reason = reason

    def _apply_session_policy(
        self,
        session: RuntimeInputSession,
        policy: InputSessionPolicy,
        reason: str | None,
    ) -> None:
        if policy is InputSessionPolicy.KEEP_LISTENING:
            return
        if policy is InputSessionPolicy.DETACH:
            session.control_state = InputControlState.DETACHED
            return
        session.control_state = InputControlState.CANCELED
        session.cancel_reason = reason

    def _conflicting_instances(
        self,
        policy: ActionAdmissionPolicy,
    ) -> tuple[ActionInstance, ...]:
        if policy.concurrency_policy == "allow_parallel" or not policy.required_locks:
            return ()
        requested = set(policy.required_locks)
        return tuple(
            instance
            for instance in self._instances
            if instance.lifecycle in {ActionLifecycle.SCHEDULED, ActionLifecycle.RUNNING}
            and requested.intersection(instance.action.admission_policy.required_locks)
        )

    def _can_interrupt(
        self,
        instance: ActionInstance,
        interrupt_kind: str | None,
        frame: int,
    ) -> bool:
        elapsed = max(0, frame - instance.start_frame)
        return instance.action.admission_policy.interrupt_policy.allows(
            interrupt_kind,
            elapsed,
        )

    def _execution_context(
        self,
        context: SimulationContext,
        instance: ActionInstance,
        frame: int,
    ) -> ActionExecutionContext:
        return ActionExecutionContext(
            frame=frame,
            instance_id=instance.instance_id,
            owner=instance.owner,
            source_session_id=instance.source_session_id,
            start_frame=instance.start_frame,
            elapsed_frames=frame - instance.start_frame,
            action_state=instance.action_state,
            simulation_context=context,
            params=instance.params,
        )

    def _record_decision(self, decision: ActionDecision) -> ActionDecision:
        self._decisions.append(decision)
        return decision

    def _instance_by_id(self, instance_id: int | None) -> ActionInstance | None:
        if instance_id is None:
            return None
        for instance in self._instances:
            if instance.instance_id == instance_id:
                return instance
        return None