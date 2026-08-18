from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from genshin_sim.application.assembly.assembler import SimulationAssembler
from genshin_sim.application.assembly.errors import AssemblyError
from genshin_sim.application.batch.models import (
    BatchDiagnostic,
    BatchMember,
    BatchMemberValidation,
    BatchValidationResult,
)
from genshin_sim.application.errors import ConfigError
from genshin_sim.application.input import SimulationInput, load_simulation_input
from genshin_sim.assets import AssetError, AssetRepository
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.content.registries import ContentUnitRegistry

logger = logging.getLogger(__name__)


class InputValidationService:
    """加载并校验 SimulationInput。"""

    def load_file(self, path: str | Path) -> SimulationInput:
        logger.debug("加载模拟输入", extra={"input_path": str(path)})
        config = load_simulation_input(path)
        logger.info(
            "模拟输入已加载",
            extra={"input_name": config.meta.name, "input_path": str(path)},
        )
        return config

    def validate_file(self, path: str | Path) -> SimulationInput:
        return self.load_file(path)

    def validate_input(self, config: SimulationInput) -> SimulationInput:
        validated = SimulationInput.from_mapping(config.to_dict())
        logger.info("模拟输入校验通过", extra={"input_name": validated.meta.name})
        return validated


class BatchInputValidationService:
    """校验已展开成员及其进入仿真所需的资产/内容依赖。

    未注入资产仓库或内容注册表时，返回 ``VALIDATION_UNAVAILABLE`` 诊断，
    不静默通过，避免把缺资产/缺 handler 的成员延迟到运行期才失败。
    """

    def __init__(
        self,
        asset_repository: AssetRepository | None = None,
        *,
        content_unit_registry: ContentUnitRegistry | None = None,
    ) -> None:
        self._input_service = InputValidationService()
        self._asset_repository = asset_repository
        self._content_unit_registry = (
            content_unit_registry
            if content_unit_registry is not None
            else (create_default_content_unit_registry() if asset_repository is not None else None)
        )

    def validate_members(self, members: Sequence[BatchMember]) -> BatchValidationResult:
        results: list[BatchMemberValidation] = []
        normalized_members: list[BatchMember] = []
        for member in members:
            details: list[BatchDiagnostic] = []
            config = self._normalize_input(member, details)
            if config is not None:
                normalized_members.append(BatchMember(item_id=member.item_id, input=config))
                details.extend(self._validate_runtime_dependencies(config, member.item_id))
            else:
                normalized_members.append(member)
            results.append(
                BatchMemberValidation(
                    item_id=member.item_id,
                    ok=not details,
                    details=tuple(details),
                )
            )

        return BatchValidationResult(
            ok=all(member.ok for member in results),
            members=tuple(results),
            normalized_members=tuple(normalized_members),
        )

    def _normalize_input(
        self,
        member: BatchMember,
        details: list[BatchDiagnostic],
    ) -> SimulationInput | None:
        try:
            if isinstance(member.input, SimulationInput):
                return self._input_service.validate_input(member.input)
            if isinstance(member.input, dict):
                return SimulationInput.from_mapping(member.input)
            # 公共类型接受 Mapping；此分支为非 dict 的映射实现保留明确诊断。
            from collections.abc import Mapping

            if isinstance(member.input, Mapping):
                return SimulationInput.from_mapping(member.input)
            raise TypeError("input 必须是 SimulationInput 或 JSON 对象")
        except (ConfigError, TypeError, ValueError) as exc:
            message = str(exc) or exc.__class__.__name__
            details.append(
                BatchDiagnostic(
                    code="CONFIG_INVALID",
                    message=message,
                    item_id=member.item_id,
                    path=_config_error_path(message),
                )
            )
            return None

    def _validate_runtime_dependencies(
        self,
        config: SimulationInput,
        item_id: str,
    ) -> tuple[BatchDiagnostic, ...]:
        if not config.team:
            return (
                BatchDiagnostic(
                    code="CONFIG_INVALID",
                    message="仿真运行至少需要一个队伍槽位",
                    item_id=item_id,
                    path="team",
                ),
            )

        repository = self._asset_repository
        registry = self._content_unit_registry
        if repository is None or registry is None:
            return (
                BatchDiagnostic(
                    code="VALIDATION_UNAVAILABLE",
                    message="缺少资产仓库或内容注册表，无法校验成员可运行性",
                    item_id=item_id,
                ),
            )

        details: list[BatchDiagnostic] = []
        for team_index, slot in enumerate(config.team):
            prefix = f"team[{team_index}]"
            try:
                character = repository.get_character(slot.character.asset_key)
            except AssetError, LookupError:
                details.append(
                    _asset_diagnostic(
                        item_id,
                        f"{prefix}.character.asset_key",
                        "角色资产不存在",
                    )
                )
                continue

            if character.handler_key is None or not registry.has_character_handler(
                character.handler_key
            ):
                details.append(
                    BatchDiagnostic(
                        code="HANDLER_UNAVAILABLE",
                        message="缺少可用角色实现",
                        item_id=item_id,
                        path=f"{prefix}.character.asset_key",
                    )
                )
            self._check_character_stats(
                repository,
                slot,
                character.asset_key,
                item_id,
                prefix,
                details,
            )
            self._check_effects(
                repository,
                registry,
                character.asset_key,
                item_id,
                f"{prefix}.character.asset_key",
                details,
            )
            for talent_key in slot.character.talents:
                try:
                    repository.get_talent_scalings(character.asset_key, talent_key)
                except AssetError, LookupError:
                    details.append(
                        _asset_diagnostic(
                            item_id,
                            f"{prefix}.character.talents.{talent_key}",
                            "角色天赋倍率数据不可用",
                            code="ASSET_UNAVAILABLE",
                        )
                    )

            if slot.weapon is not None:
                weapon_path = f"{prefix}.weapon.asset_key"
                try:
                    weapon = repository.get_weapon(slot.weapon.asset_key)
                except AssetError, LookupError:
                    details.append(_asset_diagnostic(item_id, weapon_path, "武器资产不存在"))
                else:
                    if weapon.handler_key is not None and not registry.has_weapon_handler(
                        weapon.handler_key
                    ):
                        details.append(
                            BatchDiagnostic(
                                code="HANDLER_UNAVAILABLE",
                                message="武器实现不可用",
                                item_id=item_id,
                                path=weapon_path,
                            )
                        )
                    try:
                        repository.get_weapon_level_stats(
                            weapon.asset_key,
                            slot.weapon.level,
                        )
                    except AssetError, LookupError:
                        details.append(
                            _asset_diagnostic(
                                item_id,
                                f"{prefix}.weapon.level",
                                "武器等级数据不可用",
                                code="ASSET_UNAVAILABLE",
                            )
                        )
                    self._check_effects(
                        repository,
                        registry,
                        weapon.asset_key,
                        item_id,
                        weapon_path,
                        details,
                    )

            for artifact_index, artifact_config in enumerate(slot.artifacts.sets):
                artifact_path = f"{prefix}.artifacts.sets[{artifact_index}].asset_key"
                try:
                    artifact_set = repository.get_artifact_set(artifact_config.asset_key)
                except AssetError, LookupError:
                    details.append(
                        _asset_diagnostic(item_id, artifact_path, "圣遗物套装资产不存在")
                    )
                    continue

                if artifact_set.handler_key is not None and not registry.has_artifact_handler(
                    artifact_set.handler_key
                ):
                    details.append(
                        BatchDiagnostic(
                            code="HANDLER_UNAVAILABLE",
                            message="圣遗物套装实现不可用",
                            item_id=item_id,
                            path=artifact_path,
                        )
                    )
                try:
                    bonuses = repository.get_artifact_set_bonuses(
                        artifact_set.asset_key,
                        artifact_config.pieces,
                    )
                except AssetError, LookupError:
                    details.append(
                        _asset_diagnostic(
                            item_id,
                            f"{prefix}.artifacts.sets[{artifact_index}].pieces",
                            "圣遗物套装效果数据不可用",
                            code="ASSET_UNAVAILABLE",
                        )
                    )
                else:
                    for bonus in bonuses:
                        if not registry.has_artifact_handler(bonus.handler_key):
                            details.append(
                                BatchDiagnostic(
                                    code="HANDLER_UNAVAILABLE",
                                    message="圣遗物套装效果实现不可用",
                                    item_id=item_id,
                                    path=artifact_path,
                                )
                            )
                self._check_effects(
                    repository,
                    registry,
                    artifact_set.asset_key,
                    item_id,
                    artifact_path,
                    details,
                )

        if details:
            return tuple(details)

        try:
            SimulationAssembler(
                repository,
                content_unit_registry=registry,
            ).assemble(config)
        except AssemblyError, LookupError, ValueError:
            details.append(
                BatchDiagnostic(
                    code="NOT_RUNNABLE",
                    message="输入无法组装为可运行仿真",
                    item_id=item_id,
                )
            )
        return tuple(details)

    @staticmethod
    def _check_character_stats(
        repository: AssetRepository,
        slot,
        character_key: str,
        item_id: str,
        prefix: str,
        details: list[BatchDiagnostic],
    ) -> None:
        try:
            repository.get_character_level_stats(character_key, slot.character.level)
        except AssetError, LookupError:
            details.append(
                _asset_diagnostic(
                    item_id,
                    f"{prefix}.character.level",
                    "角色等级数据不可用",
                    code="ASSET_UNAVAILABLE",
                )
            )

    @staticmethod
    def _check_effects(
        repository: AssetRepository,
        registry: ContentUnitRegistry,
        owner_key: str,
        item_id: str,
        path: str,
        details: list[BatchDiagnostic],
    ) -> None:
        try:
            effects = repository.get_effect_payloads(owner_key)
        except AssetError, LookupError:
            details.append(
                _asset_diagnostic(item_id, path, "效果数据不可用", code="ASSET_UNAVAILABLE")
            )
            return
        for effect in effects:
            if not registry.has_effect_handler(effect.handler_key):
                details.append(
                    BatchDiagnostic(
                        code="HANDLER_UNAVAILABLE",
                        message="效果实现不可用",
                        item_id=item_id,
                        path=path,
                    )
                )


def _asset_diagnostic(
    item_id: str,
    path: str,
    message: str,
    *,
    code: str = "ASSET_NOT_FOUND",
) -> BatchDiagnostic:
    return BatchDiagnostic(code=code, message=message, item_id=item_id, path=path)


def _config_error_path(message: str) -> str | None:
    known_paths = (
        "schema_version",
        "kind",
        "meta",
        "team",
        "scene",
        "input_trace",
        "rules",
        "run_options",
    )
    return next((path for path in known_paths if path in message), None)
