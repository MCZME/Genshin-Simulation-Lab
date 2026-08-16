"""装配层测试共享替身与配置构造器。"""

from __future__ import annotations

from genshin_sim.application.input import SimulationInput
from genshin_sim.core.actions import (
    ActionInterpretationResult,
    ActionInterpretationTrigger,
    ActionOwnerRef,
    InputSessionView,
    PreparedAction,
)
from genshin_sim.core.attributes import (
    STAT_CRIT_RATE,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.impacts import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.space import CreatedObjectRuntimeState


class ContributedActionInterpreter:
    supported_action_keys = ("character.runtime.skill",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context
        if session.trigger is not ActionInterpretationTrigger.RELEASE:
            return ActionInterpretationResult.wait()
        return ActionInterpretationResult.start(
            PreparedAction(
                action_key="character.runtime.skill",
                owner=ActionOwnerRef.character(session.owner.slot or 1),
                requested_start_frame=session.current_frame,
                source_session_id=session.session_id,
            )
        )


class MissingActionInterpreter:
    supported_action_keys = ("character.runtime.missing",)

    def interpret(self, context, session: InputSessionView) -> ActionInterpretationResult:
        del context, session
        return ActionInterpretationResult.wait()


class TestImpactFactory:
    def create_requests(self, context: ActionImpactContext):
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                params={"handled": True},
            ),
        )


class TestCreatedObjectBehavior:
    def create_tick_requests(self, state: CreatedObjectRuntimeState, frame: int):
        del state, frame
        return ()


class TestAttributeModifier:
    modifier_key = "modifier.test.crit_rate"
    owner_ref = "character:slot_1"
    targets = (str(STAT_CRIT_RATE),)
    scope = "attribute"
    priority = 0

    def evaluate(self, query, context):
        del query, context
        return (
            ModifierTerm(
                target_key=STAT_CRIT_RATE,
                stage=ModifierStage.FLAT_ADD,
                value=0.2,
                provider_key=self.modifier_key,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, self.modifier_key),
            ),
        )


def minimal_input(*, input_trace: list[dict[str, object]] | None = None) -> SimulationInput:
    return SimulationInput.from_mapping(
        {
            "schema_version": 2,
            "kind": "simulation_input",
            "meta": {"name": "demo", "description": ""},
            "team": [
                {
                    "slot": 1,
                    "character": {
                        "asset_key": "character:75",
                        "level": 90,
                        "constellation": 2,
                        "talents": {"normal_attack": 1},
                    },
                    "weapon": {
                        "asset_key": "weapon:11512",
                        "level": 90,
                        "refinement": 1,
                    },
                    "artifacts": {
                        "sets": [
                            {"asset_key": "artifact_set:15032", "pieces": 4},
                        ],
                        "stats": {},
                    },
                }
            ],
            "scene": {
                "player": {
                    "position": {"x": 1, "y": 0, "z": 2},
                    "facing": {"x": 0, "y": 0, "z": 1},
                },
                "targets": [
                    {
                        "id": "target_1",
                        "level": 90,
                        "position": {"x": 0, "y": 0, "z": 0},
                        "resistance": {"hydro": 0.1},
                    }
                ],
            },
            "input_trace": [] if input_trace is None else input_trace,
            "rules": {"enabled": []},
            "run_options": {"max_frames": 10},
        }
    )


def reordered_two_slot_config() -> SimulationInput:
    payload = minimal_input().to_dict()
    payload["team"] = [
        {
            "slot": 2,
            "character": {
                "asset_key": "character:electro",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        },
        {
            "slot": 1,
            "character": {
                "asset_key": "character:pyro",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        },
    ]
    return SimulationInput.from_mapping(payload)


def skill_input_trace() -> list[dict[str, object]]:
    return [
        {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    ]
