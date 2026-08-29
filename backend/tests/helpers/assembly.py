"""装配层测试共享替身与配置构造器。"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.content import create_default_content_unit_registry
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
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


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


def static_asset_input_payload(
    *,
    meta_name: str = "static asset integration",
    max_frames: int = 10,
    input_trace: list[dict[str, object]] | None = None,
    target_positions: tuple[float, ...] = (0.0,),
    target_resistances: Mapping[str, float] | None = None,
    include_weapon: bool = False,
    include_artifact_set: bool = False,
) -> dict[str, object]:
    """面向静态资产库（write_minimal_static_asset_database）的单角色仿真输入。"""

    team_member: dict[str, object] = {
        "slot": 1,
        "character": {
            "asset_key": "character:test_character",
            "level": 90,
            "constellation": 0,
            "talents": {"normal_attack": 1},
        },
        "artifacts": {"sets": [], "stats": {}},
    }
    if include_weapon:
        team_member["weapon"] = {
            "asset_key": "weapon:test_sword",
            "level": 90,
            "refinement": 1,
        }
    if include_artifact_set:
        team_member["artifacts"] = {
            "sets": [{"asset_key": "artifact_set:test_set", "pieces": 4}],
            "stats": {},
        }
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": meta_name, "description": ""},
        "team": [team_member],
        "scene": {
            "targets": [
                {
                    "id": f"target_{index}",
                    "level": 90,
                    "position": {"x": position_x, "y": 0, "z": 0},
                    "resistance": dict(target_resistances or {}),
                }
                for index, position_x in enumerate(target_positions, start=1)
            ]
        },
        "input_trace": input_trace
        or [
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": max_frames},
    }


def build_reaction_assembled(
    tmp_path: Path,
    *,
    meta_name: str = "reaction golden",
    max_frames: int = 240,
    target_positions: tuple[float, ...] = (0.0,),
    target_resistances: Mapping[str, float] | None = None,
    elemental_mastery: float | None = None,
):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    if elemental_mastery is not None:
        with sqlite3.connect(asset_db) as connection:
            cursor = connection.execute(
                """
                UPDATE character_level_stats
                SET ascension_stat = ?, ascension_value = ?
                WHERE character_key = ? AND level = ?
                """,
                ("elemental_mastery", elemental_mastery, "character:test_character", 90),
            )
        assert cursor.rowcount == 1
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
        # 测试角色绑定 runtime_probe handler，需要开发者模式注册表。
        content_unit_registry=create_default_content_unit_registry(developer_mode=True),
    ).assemble(
        SimulationInput.from_mapping(
            static_asset_input_payload(
                meta_name=meta_name,
                max_frames=max_frames,
                input_trace=[],
                target_positions=target_positions,
                target_resistances=target_resistances,
            )
        )
    )
