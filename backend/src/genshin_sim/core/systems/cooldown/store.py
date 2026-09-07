from __future__ import annotations

from collections.abc import Iterable, Mapping

from genshin_sim.core.systems.cooldown.errors import (
    CooldownDefinitionNotFoundError,
    CooldownInvariantError,
    CooldownRecordNotFoundError,
    DuplicateCooldownDefinitionError,
    DuplicateCooldownRequestError,
    StaleCooldownPlanError,
)
from genshin_sim.core.systems.cooldown.models import CooldownDefinition, CooldownKey, CooldownRecord


class CooldownDefinitionRegistry:
    def __init__(self, definitions: Iterable[CooldownDefinition] = ()) -> None:
        self._definitions: dict[CooldownKey, CooldownDefinition] = {}
        self._frozen = False
        for definition in definitions:
            self.register(definition)

    @property
    def definitions(self) -> tuple[CooldownDefinition, ...]:
        return tuple(sorted(self._definitions.values(), key=lambda item: item.key.sort_key))

    def register(self, definition: CooldownDefinition) -> None:
        if self._frozen:
            raise CooldownInvariantError("冷却定义 registry 已冻结")
        if definition.key in self._definitions:
            raise DuplicateCooldownDefinitionError(f"重复冷却定义：{definition.key}")
        self._definitions[definition.key] = definition

    def freeze(self) -> None:
        self._frozen = True

    def contains(self, key: CooldownKey) -> bool:
        return key in self._definitions

    def get(self, key: CooldownKey) -> CooldownDefinition:
        definition = self._definitions.get(key)
        if definition is None:
            raise CooldownDefinitionNotFoundError(f"冷却定义不存在：{key}")
        return definition


class CooldownStore:
    """冷却定义和运行态的唯一所有者。"""

    def __init__(self, definitions: Iterable[CooldownDefinition]) -> None:
        self.definitions = CooldownDefinitionRegistry(definitions)
        self.definitions.freeze()
        self._records = {
            definition.key: CooldownRecord(
                key=definition.key,
                ability_kind=definition.ability_kind,
                max_charges=definition.max_charges,
                available_charges=definition.max_charges,
            )
            for definition in self.definitions.definitions
        }
        self._version = 0
        self._committed_operation_ids: set[str] = set()

    @property
    def version(self) -> int:
        return self._version

    @property
    def records(self) -> tuple[CooldownRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.key.sort_key))

    def get_definition(self, key: CooldownKey) -> CooldownDefinition:
        return self.definitions.get(key)

    def get_record(self, key: CooldownKey) -> CooldownRecord:
        record = self._records.get(key)
        if record is None:
            if self.definitions.contains(key):
                raise CooldownRecordNotFoundError(f"冷却运行态不存在：{key}")
            self.definitions.get(key)
            raise AssertionError("未注册定义应已抛出异常")
        return record

    def assert_request_available(self, operation_id: str) -> None:
        if operation_id in self._committed_operation_ids:
            raise DuplicateCooldownRequestError(f"冷却请求已提交：{operation_id}")

    def assert_can_commit(
        self,
        operation_id: str | None,
        expected_store_revision: int,
        expected_records: Mapping[CooldownKey, CooldownRecord],
        additional_operation_ids: tuple[str, ...] = (),
    ) -> None:
        operation_ids = tuple(item for item in (operation_id, *additional_operation_ids) if item)
        if len(operation_ids) != len(set(operation_ids)):
            raise DuplicateCooldownRequestError("冷却提交 operation id 重复")
        if any(item in self._committed_operation_ids for item in operation_ids):
            raise DuplicateCooldownRequestError(f"冷却请求已提交：{operation_id}")
        if expected_store_revision != self._version:
            raise StaleCooldownPlanError(
                f"冷却 Store 版本冲突：expected={expected_store_revision}, actual={self._version}"
            )
        for key, expected in expected_records.items():
            actual = self.get_record(key)
            if actual != expected or actual.revision != expected.revision:
                raise StaleCooldownPlanError(f"冷却记录前值冲突：{key}")

    def commit_prevalidated(
        self,
        operation_id: str | None,
        records: Mapping[CooldownKey, CooldownRecord],
        additional_operation_ids: tuple[str, ...] = (),
    ) -> None:
        for key, record in records.items():
            if record.key != key:
                raise CooldownInvariantError("提交记录 key 不一致")
        if records:
            self._records.update(records)
            self._version += 1
        self._committed_operation_ids.update(
            item for item in (operation_id, *additional_operation_ids) if item
        )
