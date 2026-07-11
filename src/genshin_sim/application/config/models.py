from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from genshin_sim.application.config.errors import ConfigError, ConfigFileError
from genshin_sim.application.config.validation import (
    _optional_string,
    _require_asset_key,
    _require_int,
    _require_mapping,
    _require_number,
    _require_sequence,
    _require_string,
)
from genshin_sim.core.simulation import (
    SUPPORTED_INPUT_KEYS,
    KeyEvent,
    KeyInputFrame,
    KeyPhase,
)

SUPPORTED_SCHEMA_VERSION = 1
SIMULATION_CONFIG_KIND = "simulation_config"


@dataclass(frozen=True, slots=True)
class SimulationMeta:
    name: str = "Untitled Simulation"
    description: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SimulationMeta:
        name = raw.get("name", "Untitled Simulation")
        description = raw.get("description", "")
        return cls(
            name=_require_string(name, "meta.name"),
            description=_optional_string(description, "meta.description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description}


@dataclass(frozen=True, slots=True)
class CharacterConfig:
    asset_key: str
    level: int
    constellation: int = 0
    talents: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> CharacterConfig:
        asset_key = _require_asset_key(raw.get("asset_key"), "character", f"{path}.asset_key")
        level = _require_int(raw.get("level"), f"{path}.level")
        if level <= 0:
            raise ConfigError(f"{path}.level 必须是正整数")

        constellation = _require_int(raw.get("constellation", 0), f"{path}.constellation")
        if not 0 <= constellation <= 6:
            raise ConfigError(f"{path}.constellation 必须在 0 到 6 之间")

        talents_raw = _require_mapping(raw.get("talents", {}), f"{path}.talents")
        talents: dict[str, int] = {}
        for talent_name, talent_level_raw in talents_raw.items():
            talent_name = _require_string(talent_name, f"{path}.talents key")
            talent_level = _require_int(talent_level_raw, f"{path}.talents.{talent_name}")
            if talent_level <= 0:
                raise ConfigError(f"{path}.talents.{talent_name} 必须是正整数")
            talents[talent_name] = talent_level

        return cls(
            asset_key=asset_key,
            level=level,
            constellation=constellation,
            talents=talents,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_key": self.asset_key,
            "level": self.level,
            "constellation": self.constellation,
            "talents": dict(self.talents),
        }


@dataclass(frozen=True, slots=True)
class WeaponConfig:
    asset_key: str
    level: int
    refinement: int = 1

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> WeaponConfig:
        asset_key = _require_asset_key(raw.get("asset_key"), "weapon", f"{path}.asset_key")
        level = _require_int(raw.get("level"), f"{path}.level")
        if level <= 0:
            raise ConfigError(f"{path}.level 必须是正整数")

        refinement = _require_int(raw.get("refinement", 1), f"{path}.refinement")
        if not 1 <= refinement <= 5:
            raise ConfigError(f"{path}.refinement 必须在 1 到 5 之间")

        return cls(asset_key=asset_key, level=level, refinement=refinement)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_key": self.asset_key,
            "level": self.level,
            "refinement": self.refinement,
        }


@dataclass(frozen=True, slots=True)
class ArtifactSetConfig:
    asset_key: str
    pieces: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> ArtifactSetConfig:
        asset_key = _require_asset_key(
            raw.get("asset_key"),
            "artifact_set",
            f"{path}.asset_key",
        )
        pieces = _require_int(raw.get("pieces"), f"{path}.pieces")
        if pieces <= 0:
            raise ConfigError(f"{path}.pieces 必须是正整数")
        return cls(asset_key=asset_key, pieces=pieces)

    def to_dict(self) -> dict[str, Any]:
        return {"asset_key": self.asset_key, "pieces": self.pieces}


@dataclass(frozen=True, slots=True)
class ArtifactConfig:
    sets: tuple[ArtifactSetConfig, ...] = ()
    stats: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> ArtifactConfig:
        sets = tuple(
            ArtifactSetConfig.from_mapping(
                _require_mapping(item, f"{path}.sets[{index}]"),
                f"{path}.sets[{index}]",
            )
            for index, item in enumerate(_require_sequence(raw.get("sets", []), f"{path}.sets"))
        )
        stats = dict(_require_mapping(raw.get("stats", {}), f"{path}.stats"))
        return cls(sets=sets, stats=stats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sets": [artifact_set.to_dict() for artifact_set in self.sets],
            "stats": dict(self.stats),
        }


@dataclass(frozen=True, slots=True)
class TeamSlotConfig:
    slot: int
    character: CharacterConfig
    weapon: WeaponConfig | None = None
    artifacts: ArtifactConfig = field(default_factory=ArtifactConfig)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> TeamSlotConfig:
        slot = _require_int(raw.get("slot"), f"{path}.slot")
        if slot <= 0:
            raise ConfigError(f"{path}.slot 必须是正整数")

        character = CharacterConfig.from_mapping(
            _require_mapping(raw.get("character"), f"{path}.character"),
            f"{path}.character",
        )
        weapon_raw = raw.get("weapon")
        weapon = (
            None
            if weapon_raw is None
            else WeaponConfig.from_mapping(
                _require_mapping(weapon_raw, f"{path}.weapon"),
                f"{path}.weapon",
            )
        )
        artifacts = ArtifactConfig.from_mapping(
            _require_mapping(raw.get("artifacts", {}), f"{path}.artifacts"),
            f"{path}.artifacts",
        )
        return cls(slot=slot, character=character, weapon=weapon, artifacts=artifacts)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "slot": self.slot,
            "character": self.character.to_dict(),
            "artifacts": self.artifacts.to_dict(),
        }
        if self.weapon is not None:
            payload["weapon"] = self.weapon.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class Vector3Config:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> Vector3Config:
        return cls(
            x=_require_number(raw.get("x", 0.0), f"{path}.x"),
            y=_require_number(raw.get("y", 0.0), f"{path}.y"),
            z=_require_number(raw.get("z", 0.0), f"{path}.z"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "z": self.z}


def _default_facing_config() -> Vector3Config:
    return Vector3Config(0.0, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class ScenePlayerConfig:
    position: Vector3Config = field(default_factory=Vector3Config)
    facing: Vector3Config = field(default_factory=_default_facing_config)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ScenePlayerConfig:
        position = Vector3Config.from_mapping(
            _require_mapping(raw.get("position", {}), "scene.player.position"),
            "scene.player.position",
        )
        facing = Vector3Config.from_mapping(
            _require_mapping(raw.get("facing", {"z": 1.0}), "scene.player.facing"),
            "scene.player.facing",
        )
        if facing.x == 0 and facing.z == 0:
            raise ConfigError("scene.player.facing 的 X/Z 方向不能同时为 0")
        return cls(position=position, facing=facing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "facing": self.facing.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SceneTargetConfig:
    target_id: str
    level: int | None = None
    position: Vector3Config = field(default_factory=Vector3Config)
    resistance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> SceneTargetConfig:
        target_id = _require_string(raw.get("id"), f"{path}.id")
        level_raw = raw.get("level")
        level = None if level_raw is None else _require_int(level_raw, f"{path}.level")
        if level is not None and level <= 0:
            raise ConfigError(f"{path}.level 必须是正整数")
        position = Vector3Config.from_mapping(
            _require_mapping(raw.get("position", {}), f"{path}.position"),
            f"{path}.position",
        )
        resistance = dict(_require_mapping(raw.get("resistance", {}), f"{path}.resistance"))
        return cls(target_id=target_id, level=level, position=position, resistance=resistance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.target_id,
            "level": self.level,
            "position": self.position.to_dict(),
            "resistance": dict(self.resistance),
        }


@dataclass(frozen=True, slots=True)
class SceneConfig:
    player: ScenePlayerConfig = field(default_factory=ScenePlayerConfig)
    targets: tuple[SceneTargetConfig, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SceneConfig:
        player = ScenePlayerConfig.from_mapping(
            _require_mapping(raw.get("player", {}), "scene.player")
        )
        targets = tuple(
            SceneTargetConfig.from_mapping(
                _require_mapping(item, f"scene.targets[{index}]"),
                f"scene.targets[{index}]",
            )
            for index, item in enumerate(_require_sequence(raw.get("targets", []), "scene.targets"))
        )
        target_ids = [target.target_id for target in targets]
        if len(target_ids) != len(set(target_ids)):
            raise ConfigError("scene.targets 不能包含重复 id")
        return cls(player=player, targets=targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player.to_dict(),
            "targets": [target.to_dict() for target in self.targets],
        }


@dataclass(frozen=True, slots=True)
class KeyEventConfig:
    key: str
    phase: KeyPhase

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> KeyEventConfig:
        key = _require_string(raw.get("key"), f"{path}.key")
        if key not in SUPPORTED_INPUT_KEYS:
            raise ConfigError(f"不支持的输入按键：{key}")
        phase_raw = _require_string(raw.get("phase"), f"{path}.phase")
        try:
            phase = KeyPhase(phase_raw)
        except ValueError as exc:
            raise ConfigError(f"{path}.phase 必须是 'press' 或 'release'") from exc
        return cls(key=key, phase=phase)

    def to_core(self) -> KeyEvent:
        return KeyEvent(self.key, self.phase)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "phase": self.phase.value}


@dataclass(frozen=True, slots=True)
class InputFrameConfig:
    frame: int
    events: tuple[KeyEventConfig, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], path: str) -> InputFrameConfig:
        frame = _require_int(raw.get("frame"), f"{path}.frame")
        events = tuple(
            KeyEventConfig.from_mapping(
                _require_mapping(item, f"{path}.events[{index}]"),
                f"{path}.events[{index}]",
            )
            for index, item in enumerate(_require_sequence(raw.get("events", []), f"{path}.events"))
        )
        return cls(frame=frame, events=events)

    def to_core(self) -> KeyInputFrame:
        return KeyInputFrame(
            frame=self.frame,
            events=tuple(event.to_core() for event in self.events),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"frame": self.frame, "events": [event.to_dict() for event in self.events]}


@dataclass(frozen=True, slots=True)
class RuleConfig:
    """规则配置的临时占位结构。

    当前只保留启用规则列表，具体形式等待规则系统实现方式确定后再细化。
    """

    enabled: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> RuleConfig:
        enabled = tuple(
            _require_string(item, f"rules.enabled[{index}]")
            for index, item in enumerate(_require_sequence(raw.get("enabled", []), "rules.enabled"))
        )
        return cls(enabled=enabled)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": list(self.enabled)}


@dataclass(frozen=True, slots=True)
class RunOptions:
    max_frames: int = 18000

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> RunOptions:
        max_frames = _require_int(raw.get("max_frames", 18000), "run_options.max_frames")
        if max_frames <= 0:
            raise ConfigError("run_options.max_frames 必须是正整数")
        return cls(max_frames=max_frames)

    def to_dict(self) -> dict[str, Any]:
        return {"max_frames": self.max_frames}


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    schema_version: int
    kind: str
    meta: SimulationMeta = field(default_factory=SimulationMeta)
    team: tuple[TeamSlotConfig, ...] = ()
    scene: SceneConfig = field(default_factory=SceneConfig)
    input_trace: tuple[InputFrameConfig, ...] = ()
    rules: RuleConfig = field(default_factory=RuleConfig)
    run_options: RunOptions = field(default_factory=RunOptions)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SimulationConfig:
        schema_version = _require_int(raw.get("schema_version"), "schema_version")
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ConfigError(f"不支持的 schema_version：{schema_version}")

        kind = _require_string(raw.get("kind"), "kind")
        if kind != SIMULATION_CONFIG_KIND:
            raise ConfigError(f"kind 必须是 {SIMULATION_CONFIG_KIND!r}")

        team = tuple(
            TeamSlotConfig.from_mapping(
                _require_mapping(item, f"team[{index}]"),
                f"team[{index}]",
            )
            for index, item in enumerate(_require_sequence(raw.get("team", []), "team"))
        )
        _validate_team_slots(team)

        input_trace = tuple(
            InputFrameConfig.from_mapping(
                _require_mapping(item, f"input_trace[{index}]"),
                f"input_trace[{index}]",
            )
            for index, item in enumerate(
                _require_sequence(raw.get("input_trace", []), "input_trace")
            )
        )
        _validate_input_trace(input_trace)

        return cls(
            schema_version=schema_version,
            kind=kind,
            meta=SimulationMeta.from_mapping(_require_mapping(raw.get("meta", {}), "meta")),
            team=team,
            scene=SceneConfig.from_mapping(_require_mapping(raw.get("scene", {}), "scene")),
            input_trace=input_trace,
            rules=RuleConfig.from_mapping(_require_mapping(raw.get("rules", {}), "rules")),
            run_options=RunOptions.from_mapping(
                _require_mapping(raw.get("run_options", {}), "run_options")
            ),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> SimulationConfig:
        config_path = Path(path)
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigFileError(f"无法读取配置文件：{config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigFileError(f"配置文件不是有效 JSON：{config_path}") from exc
        return cls.from_mapping(_require_mapping(payload, "config"))

    def to_core_input_frames(self) -> tuple[KeyInputFrame, ...]:
        return tuple(frame.to_core() for frame in self.input_trace)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "meta": self.meta.to_dict(),
            "team": [slot.to_dict() for slot in self.team],
            "scene": self.scene.to_dict(),
            "input_trace": [frame.to_dict() for frame in self.input_trace],
            "rules": self.rules.to_dict(),
            "run_options": self.run_options.to_dict(),
        }

    def write_json_file(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_simulation_config(path: str | Path) -> SimulationConfig:
    return SimulationConfig.from_json_file(path)


def _validate_team_slots(team: tuple[TeamSlotConfig, ...]) -> None:
    if len(team) > 4:
        raise ConfigError("team 最多只能包含 4 个槽位")
    slots = [item.slot for item in team]
    if len(slots) != len(set(slots)):
        raise ConfigError("team 槽位不能重复")
    if slots and sorted(slots) != list(range(1, len(slots) + 1)):
        raise ConfigError("team 槽位必须从 1 开始连续排列")


def _validate_input_trace(input_trace: tuple[InputFrameConfig, ...]) -> None:
    previous_frame = -1
    pressed_keys: set[str] = set()

    for input_frame in input_trace:
        if input_frame.frame <= 0:
            raise ConfigError("input_trace 帧号必须是正整数")
        if input_frame.frame <= previous_frame:
            raise ConfigError("input_trace 帧号必须严格递增")
        previous_frame = input_frame.frame

        keys_in_frame: set[str] = set()
        for event in input_frame.events:
            if event.key in keys_in_frame:
                raise ConfigError(f"第 {input_frame.frame} 帧存在重复按键：{event.key}")
            keys_in_frame.add(event.key)

            if event.phase is KeyPhase.PRESS:
                if event.key in pressed_keys:
                    raise ConfigError(f"按键已经处于按下状态：{event.key}")
                pressed_keys.add(event.key)
                continue

            if event.key not in pressed_keys:
                raise ConfigError(f"按键在按下前被释放：{event.key}")
            pressed_keys.remove(event.key)

    if pressed_keys:
        keys = ", ".join(sorted(pressed_keys))
        raise ConfigError(f"输入轨迹结束时仍有按键未释放：{keys}")
