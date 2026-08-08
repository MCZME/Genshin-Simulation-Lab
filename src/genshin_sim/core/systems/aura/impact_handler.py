"""角色侧元素附着的窄适配：只结算附着与 ICD，不进入敌方 Reaction 流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.elements import ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.events import (
    AuraAppliedPayload,
    AuraIcdResolvedPayload,
    EventEngine,
    EventType,
    GameEvent,
)
from genshin_sim.core.systems.aura.models import AuraApplicationRequest
from genshin_sim.core.systems.aura.runtime import AuraRuntime
from genshin_sim.core.systems.aura_icd import (
    AuraIcdAttackerRef,
    AuraIcdRuntime,
    IcdBinding,
    IcdImpactRequest,
)

if TYPE_CHECKING:
    from genshin_sim.core.impacts.models import ImpactRequest


@dataclass(frozen=True, slots=True)
class CharacterAuraImpactRecord:
    """一次角色附着请求的提交记录。"""

    frame: int
    impact_request: ImpactRequest
    subject_refs: tuple[ElementalSubjectRef, ...]
    icd_request_ids: tuple[str, ...]
    aura_request_ids: tuple[str, ...]


class CharacterAuraImpactRequestHandler:
    """把针对角色的 APPLY_AURA 请求结算为 Aura 附着（含 ICD）。"""

    def __init__(
        self,
        aura_runtime: AuraRuntime,
        icd_runtime: AuraIcdRuntime,
        event_engine: EventEngine | None = None,
    ) -> None:
        self.aura_runtime = aura_runtime
        self.icd_runtime = icd_runtime
        self.event_engine = event_engine
        self._records: list[CharacterAuraImpactRecord] = []

    @property
    def records(self) -> tuple[CharacterAuraImpactRecord, ...]:
        return tuple(self._records)

    def is_character_aura_request(self, request: ImpactRequest) -> bool:
        if request.kind.value != "apply_aura" or request.elemental_application_spec is None:
            return False
        if not request.target_refs:
            return False
        return all(self._is_character_ref(ref) for ref in request.target_refs)

    @staticmethod
    def _is_character_ref(target_ref: str) -> bool:
        return target_ref == "player:active" or target_ref.startswith("character:")

    def handle_impact_request(
        self,
        context: object,
        request: ImpactRequest,
    ) -> CharacterAuraImpactRecord:
        if not self.is_character_aura_request(request):
            raise ValueError("角色附着请求目标必须全部是角色主体")
        if request.owner_slot is None:
            raise ValueError("角色附着请求必须提供 owner_slot")
        spec = request.elemental_application_spec
        if spec is None:
            raise ValueError("角色附着请求缺少 ElementalApplicationSpec")
        root_work_id = request.request_id or request.source_impact_point_id
        if root_work_id is None:
            raise ValueError("角色附着请求必须提供 request_id 或 source_impact_point_id")
        frame = request.frame
        self.aura_runtime.update_frame(context, frame)
        self.icd_runtime.update_frame(context, frame)
        batch_id = f"character-aura:{frame}:{root_work_id}"
        icd_planner = self.icd_runtime.begin_batch(frame, batch_id)
        aura_planner = self.aura_runtime.begin_batch(frame, batch_id)
        source_ref = ElementalSourceRef(
            f"character:slot_{request.owner_slot}",
            root_work_id,
        )
        subject_refs: list[ElementalSubjectRef] = []
        for order, target_ref in enumerate(request.target_refs):
            subject_ref = self._resolve_subject(context, target_ref)
            subject_refs.append(subject_ref)
            icd_request = IcdImpactRequest(
                request_id=f"{root_work_id}:target:{target_ref}:icd",
                impact_ref=f"{spec.impact_ref}:target:{target_ref}",
                frame=frame,
                order=order,
                attacker_ref=AuraIcdAttackerRef(
                    f"character:slot_{request.owner_slot}"
                ),
                defender_ref=subject_ref,
                binding=self._binding_for(spec),
            )
            icd = icd_planner.prepare(icd_request)
            if icd.coefficient.is_zero:
                continue
            aura_planner.apply(
                AuraApplicationRequest(
                    request_id=f"{root_work_id}:target:{target_ref}:aura",
                    application_id=(
                        f"{root_work_id}:target:{target_ref}:application"
                    ),
                    impact_ref=f"{spec.impact_ref}:target:{target_ref}",
                    frame=frame,
                    order=order,
                    source_ref=source_ref,
                    target_ref=subject_ref,
                    element=spec.element,
                    base_strength=spec.elemental_strength,
                    application_coefficient=icd.coefficient,
                    effective_raw_amount=spec.elemental_amount,
                )
            )
        icd_plan = icd_planner.seal()
        aura_plan = aura_planner.seal()
        self.icd_runtime.validate(icd_plan)
        self.aura_runtime.validate(aura_plan)
        self.icd_runtime.commit_prevalidated(icd_plan)
        self.aura_runtime.commit_prevalidated(aura_plan)
        if self.event_engine is not None:
            with self.aura_runtime.event_publication_guard():
                for resolution in icd_plan.resolutions:
                    self.event_engine.publish(
                        GameEvent(
                            EventType.AURA_ICD_RESOLVED,
                            frame,
                            AuraIcdResolvedPayload(resolution),
                        )
                    )
                for result in aura_plan.application_results:
                    self.event_engine.publish(
                        GameEvent(
                            EventType.AURA_APPLIED,
                            frame,
                            AuraAppliedPayload(result),
                        )
                    )
        record = CharacterAuraImpactRecord(
            frame=frame,
            impact_request=request,
            subject_refs=tuple(subject_refs),
            icd_request_ids=icd_plan.request_ids,
            aura_request_ids=tuple(
                result.request_id for result in aura_plan.application_results
            ),
        )
        self._records.append(record)
        return record

    @staticmethod
    def _resolve_subject(
        context: object,
        target_ref: str,
    ) -> ElementalSubjectRef:
        if target_ref.startswith("character:"):
            return ElementalSubjectRef.character(target_ref)
        if target_ref == "player:active":
            space_runtime = getattr(context, "space_runtime", None)
            team_state = getattr(space_runtime, "team_state", None)
            if team_state is None:
                raise ValueError("角色附着目标解析缺少队伍运行态")
            return ElementalSubjectRef.character(
                team_state.current_character.combat_entity_id
            )
        raise ValueError(f"不支持的字符角色附着目标：{target_ref}")

    @staticmethod
    def _binding_for(spec) -> IcdBinding | None:
        if spec.icd_label_key is None:
            return None
        assert spec.icd_definition_key is not None
        return IcdBinding(spec.icd_label_key, spec.icd_definition_key)
