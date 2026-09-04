"""芭芭拉内容属性修饰：命座 2 的水元素伤害加成 provider。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CONSTELLATION_C2_HYDRO_PROVIDER_KEY,
)
from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    AttributeQuery,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
)


class _SpatialEntityPort(Protocol):
    owner_key: str | None


class _CreatedObjectStatePort(Protocol):
    object_key: str
    entity: _SpatialEntityPort

    def is_active_at(self, frame: int) -> bool: ...


class _CreatedObjectRuntimePort(Protocol):
    @property
    def objects(self) -> Sequence[_CreatedObjectStatePort]: ...


class _CharacterRuntimePort(Protocol):
    combat_entity_id: str


class _TeamRuntimeStatePort(Protocol):
    @property
    def current_character(self) -> _CharacterRuntimePort: ...


class BarbaraConstellationC2HydroBonusProvider:
    """环活动期间为当前场上角色实时提供水元素伤害加成。"""

    def __init__(
        self,
        *,
        slot: int,
        bonus_value: float,
        object_key: str,
    ) -> None:
        self._slot = slot
        self._bonus_value = float(bonus_value)
        self._object_key = object_key
        self._created_object_runtime: _CreatedObjectRuntimePort | None = None
        self._team_state: _TeamRuntimeStatePort | None = None
        self.provider_spec = ModifierProviderSpec(
            provider_key=BARBARA_CONSTELLATION_C2_HYDRO_PROVIDER_KEY,
            writes=frozenset({BONUS_DAMAGE_HYDRO}),
            display_name="华彩圆舞曲·环水伤加成",
        )

    def bind_runtime_ports(
        self,
        created_object_runtime: _CreatedObjectRuntimePort,
        team_state: _TeamRuntimeStatePort,
    ) -> None:
        """装配阶段原位绑定创建物运行时与队伍运行时。"""

        self._created_object_runtime = created_object_runtime
        self._team_state = team_state

    def contribute(
        self,
        query: AttributeQuery,
        session: object,
    ) -> Sequence[ModifierTerm]:
        del session
        if query.attribute_key != BONUS_DAMAGE_HYDRO:
            return ()
        if self._created_object_runtime is None or self._team_state is None:
            return ()
        if not self._ring_active(query.frame):
            return ()
        current = self._team_state.current_character
        if current.combat_entity_id != query.subject_ref.entity_id:
            return ()
        return (
            ModifierTerm(
                target_key=BONUS_DAMAGE_HYDRO,
                stage=ModifierStage.FLAT_ADD,
                value=self._bonus_value,
                provider_key=BARBARA_CONSTELLATION_C2_HYDRO_PROVIDER_KEY,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    BARBARA_CONSTELLATION_C2_HYDRO_PROVIDER_KEY,
                ),
            ),
        )

    def _ring_active(self, frame: int) -> bool:
        runtime = self._created_object_runtime
        if runtime is None:
            return False
        return any(
            obj.object_key == self._object_key
            and obj.entity.owner_key == f"slot:{self._slot}"
            and obj.is_active_at(frame)
            for obj in runtime.objects
        )
