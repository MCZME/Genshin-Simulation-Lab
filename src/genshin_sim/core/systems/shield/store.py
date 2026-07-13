from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace

from genshin_sim.core.mechanics import MechanicInstanceStore
from genshin_sim.core.systems.shield.errors import (
    ShieldAtomicCommitError,
    ShieldInstanceNotFoundError,
    ShieldValidationError,
)
from genshin_sim.core.systems.shield.formulas import (
    validate_non_negative_shield_float,
    validate_shield_float,
)
from genshin_sim.core.systems.shield.models import ShieldComponent, ShieldProtectionRef


@dataclass(frozen=True, slots=True)
class ShieldComponentUpdate:
    instance_id: int
    expected_remaining: float
    remaining_after: float
    maximum_after: float
    remove_after: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.instance_id, bool) or not isinstance(self.instance_id, int):
            raise ShieldValidationError("instance_id 必须是正整数")
        if self.instance_id <= 0:
            raise ShieldValidationError("instance_id 必须是正整数")
        object.__setattr__(
            self,
            "expected_remaining",
            validate_shield_float(self.expected_remaining, "expected_remaining"),
        )
        object.__setattr__(
            self,
            "remaining_after",
            validate_non_negative_shield_float(self.remaining_after, "remaining_after"),
        )
        maximum = validate_shield_float(self.maximum_after, "maximum_after")
        if maximum <= 0:
            raise ShieldValidationError("maximum_after 必须是正数")
        object.__setattr__(self, "maximum_after", maximum)
        if self.remove_after != (self.remaining_after == 0):
            raise ShieldValidationError("remove_after 必须与 remaining_after 是否为零一致")
        if self.remaining_after > self.maximum_after:
            raise ShieldValidationError("remaining_after 不能大于 maximum_after")


class ShieldComponentStore:
    """按 mechanic instance id 保存活动护盾组件。"""

    __slots__ = ("_components", "_version")

    def __init__(self, components: Iterable[ShieldComponent] = ()) -> None:
        self._components: dict[int, ShieldComponent] = {}
        self._version = 0
        for component in components:
            self.add(component)

    @property
    def version(self) -> int:
        return self._version

    def get(self, instance_id: int) -> ShieldComponent | None:
        return self._components.get(instance_id)

    def require(self, instance_id: int) -> ShieldComponent:
        component = self.get(instance_id)
        if component is None:
            raise ShieldInstanceNotFoundError(f"护盾组件不存在：{instance_id}")
        return component

    def add(self, component: ShieldComponent) -> ShieldComponent:
        if not isinstance(component, ShieldComponent):
            raise ShieldValidationError("component 必须是 ShieldComponent")
        if component.instance_id in self._components:
            raise ShieldValidationError(f"护盾组件实例 id 重复：{component.instance_id}")
        self._components[component.instance_id] = component
        self._version += 1
        return component

    def replace(self, component: ShieldComponent) -> ShieldComponent:
        self.require(component.instance_id)
        self._components[component.instance_id] = component
        self._version += 1
        return component

    def remove(self, instance_id: int) -> ShieldComponent:
        component = self.require(instance_id)
        del self._components[instance_id]
        self._version += 1
        return component

    def discard(self, instance_id: int) -> ShieldComponent | None:
        component = self._components.pop(instance_id, None)
        if component is not None:
            self._version += 1
        return component

    def active_for(
        self,
        protection_ref: ShieldProtectionRef,
        *,
        frame: int,
        instance_store: MechanicInstanceStore,
    ) -> tuple[ShieldComponent, ...]:
        components = []
        owner_key = protection_ref.to_key()
        for instance in instance_store.active_instances(
            frame=frame,
            owner_ref=owner_key,
            capability_key="shield",
        ):
            component = self._components.get(instance.instance_id)
            if component is not None and component.protection_ref == protection_ref:
                components.append(component)
        return tuple(sorted(components, key=lambda item: item.instance_id))

    def conflicts(
        self,
        protection_ref: ShieldProtectionRef,
        conflict_key: str,
        *,
        frame: int,
        instance_store: MechanicInstanceStore,
    ) -> tuple[ShieldComponent, ...]:
        return tuple(
            component
            for component in self.active_for(
                protection_ref,
                frame=frame,
                instance_store=instance_store,
            )
            if component.conflict_key == conflict_key
        )

    def apply_batch(
        self,
        updates: Iterable[ShieldComponentUpdate],
        *,
        expected_version: int,
    ) -> tuple[ShieldComponent, ...]:
        update_tuple = tuple(sorted(updates, key=lambda item: item.instance_id))
        if expected_version != self._version:
            raise ShieldAtomicCommitError(
                f"护盾组件版本冲突：expected={expected_version}, actual={self._version}"
            )
        instance_ids = [update.instance_id for update in update_tuple]
        if len(instance_ids) != len(set(instance_ids)):
            raise ShieldAtomicCommitError("批量护盾更新包含重复 instance_id")

        originals: list[ShieldComponent] = []
        replacements: dict[int, ShieldComponent | None] = {}
        for update in update_tuple:
            component = self.get(update.instance_id)
            if component is None:
                raise ShieldAtomicCommitError(f"护盾组件不存在：{update.instance_id}")
            if not math.isclose(
                component.remaining_native_absorption,
                update.expected_remaining,
                rel_tol=0.0,
                abs_tol=0.0,
            ):
                raise ShieldAtomicCommitError(f"护盾组件前值冲突：{update.instance_id}")
            originals.append(component)
            if update.remove_after:
                replacements[update.instance_id] = None
            else:
                replacements[update.instance_id] = replace(
                    component,
                    remaining_native_absorption=update.remaining_after,
                    maximum_native_absorption=update.maximum_after,
                )

        for instance_id, replacement in replacements.items():
            if replacement is None:
                del self._components[instance_id]
            else:
                self._components[instance_id] = replacement
        if update_tuple:
            self._version += 1
        return tuple(originals)

    @property
    def components(self) -> tuple[ShieldComponent, ...]:
        return tuple(sorted(self._components.values(), key=lambda item: item.instance_id))
