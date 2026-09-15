"""装配期构造的跨领域窄只读端口适配器。"""

from __future__ import annotations

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.elements import AuraKind, ElementalSubjectKind, ElementalSubjectRef
from genshin_sim.core.simulation.team import TeamRuntimeState
from genshin_sim.core.systems.reaction.runtime import ReactionRuntime
from genshin_sim.core.systems.shield.enums import ShieldProtectionKind
from genshin_sim.core.systems.shield.runtime import ShieldRuntime


class AuraFrozenReadAdapter:
    """通过 Aura 与 Reaction 运行态查询目标冰附着/冻结状态。"""

    def __init__(
        self,
        aura_runtime,
        reaction_runtime: ReactionRuntime,
    ) -> None:
        self._aura_runtime = aura_runtime
        self._reaction_runtime = reaction_runtime

    def has_cryo_or_frozen(
        self,
        target_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool:
        del frame
        subject = ElementalSubjectRef(
            ElementalSubjectKind(target_ref.kind.value),
            target_ref.entity_id,
        )
        view = self._aura_runtime.view(subject)
        if view.component_for(AuraKind.CRYO) is not None:
            return True
        return self._reaction_runtime.frozen_state_for(subject) is not None


class ShieldPresenceReadAdapter:
    """通过护盾 Store 与队伍运行态查询角色护盾庇护。"""

    def __init__(
        self,
        shield_runtime: ShieldRuntime,
        team_state: TeamRuntimeState,
    ) -> None:
        self._shield_runtime = shield_runtime
        self._team_state = team_state

    def has_active_shield(
        self,
        character_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool:
        for record in self._shield_runtime.shield_store.active(frame=frame):
            protection = record.state.protection_ref
            if (
                protection.kind is ShieldProtectionKind.CHARACTER
                and protection.protection_id == character_ref.entity_id
            ):
                return True
            if protection.kind is ShieldProtectionKind.ACTIVE_TEAM:
                current = AttributeSubjectRef.character(
                    self._team_state.current_character.combat_entity_id
                )
                if current == character_ref:
                    return True
        return False


class LunarCagePresenceReadAdapter:
    """通过 Reaction 运行态查询是否存在活动月笼（第一版不判距离）。"""

    def __init__(self, reaction_runtime: ReactionRuntime) -> None:
        self._reaction_runtime = reaction_runtime

    def has_active_lunar_cage(self) -> bool:
        return bool(self._reaction_runtime.active_lunar_cages())


class TeamScopeProjectionAdapter:
    """用队伍运行态回答角色主体所属队伍作用域与当前场上角色判定。

    队伍作用域 id 由装配期显式传入，不在此处硬编码，也不从空间实体 id 推导。
    """

    def __init__(self, team_state: TeamRuntimeState, *, team_ref: str) -> None:
        self._team_state = team_state
        self._team_ref = team_ref

    def team_scope_for(self, character_ref: AttributeSubjectRef) -> str | None:
        if self._character(character_ref) is None:
            return None
        return self._team_ref

    def is_active_character(self, character_ref: AttributeSubjectRef) -> bool:
        character = self._character(character_ref)
        if character is None:
            return False
        return character.slot == self._team_state.active_slot

    def _character(self, character_ref: AttributeSubjectRef):
        if character_ref.kind is not AttributeSubjectKind.CHARACTER:
            return None
        for character in self._team_state.characters:
            if character.combat_entity_id == character_ref.entity_id:
                return character
        return None
