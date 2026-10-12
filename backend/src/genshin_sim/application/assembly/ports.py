"""装配期构造的跨领域窄只读端口适配器。"""

from __future__ import annotations

from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.elements import (
    AuraKind,
    Element,
    ElementalSubjectKind,
    ElementalSubjectRef,
    affected_aura_kinds,
)
from genshin_sim.core.simulation.team import TeamRuntimeState
from genshin_sim.core.systems.buff.models import BuffRecord
from genshin_sim.core.systems.buff.protocols import BuffReader
from genshin_sim.core.systems.health.runtime import HealthRuntime
from genshin_sim.core.systems.reaction.runtime import ReactionRuntime
from genshin_sim.core.systems.shield.enums import ShieldProtectionKind
from genshin_sim.core.systems.shield.runtime import ShieldRuntime


class HealthReadAdapter:
    """通过 HealthRuntime 查询角色当前生命比值。"""

    def __init__(self, health_runtime: HealthRuntime) -> None:
        self._health_runtime = health_runtime

    def hp_ratio(self, character_ref: AttributeSubjectRef, frame: int) -> float:
        return self._health_runtime.get_hp_ratio(character_ref, frame)


class TargetElementAuraReadAdapter:
    """通过 Aura 与 Reaction 运行态查询目标的元素影响与冻结状态。

    面向条件效果（圣遗物、武器、元素共鸣）的窄只读端口实现：只回答「目标是否
    受某元素影响」「目标是否处于冻结状态」，不暴露 Aura 记录细节。元素影响口径
    来自 ``core.elements.affected_aura_kinds``（燃烧归火、冻结归冰、激化归草）；
    冻结在持久 Aura 分量之外还可能只以 Reaction 冻结状态呈现，故对含冻结归属的
    元素一并查询冻结状态。
    """

    def __init__(
        self,
        aura_runtime,
        reaction_runtime: ReactionRuntime,
    ) -> None:
        self._aura_runtime = aura_runtime
        self._reaction_runtime = reaction_runtime

    def is_affected_by(
        self,
        target_ref: AttributeSubjectRef,
        element: Element,
        frame: int,
    ) -> bool:
        del frame
        kinds = affected_aura_kinds(element)
        if not kinds:
            return False
        subject = self._elemental_subject(target_ref)
        view = self._aura_runtime.view(subject)
        if any(view.component_for(aura_kind) is not None for aura_kind in kinds):
            return True
        return AuraKind.FROZEN in kinds and self._is_frozen(subject)

    def is_frozen(self, target_ref: AttributeSubjectRef, frame: int) -> bool:
        del frame
        return self._is_frozen(self._elemental_subject(target_ref))

    def _is_frozen(self, subject: ElementalSubjectRef) -> bool:
        return self._reaction_runtime.frozen_state_for(subject) is not None

    def _elemental_subject(self, target_ref: AttributeSubjectRef) -> ElementalSubjectRef:
        return ElementalSubjectRef(
            ElementalSubjectKind(target_ref.kind.value),
            target_ref.entity_id,
        )


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


class TargetBuffPresenceReadAdapter:
    """通过 Buff 只读查询目标在指定帧的 Buff 存在性与活动层数。

    供内容侧条件伤害修饰使用：只回答存在性与层数，不暴露 Buff 实例细节。
    """

    def __init__(self, buff_reader: BuffReader) -> None:
        self._buff_reader = buff_reader

    def _records(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> tuple[BuffRecord, ...]:
        return self._buff_reader.active(
            frame,
            target_ref=target_ref,
            definition_key=definition_key,
        )

    def has_buff(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> bool:
        return bool(
            self._records(
                target_ref=target_ref,
                definition_key=definition_key,
                frame=frame,
            )
        )

    def active_stack_count(
        self,
        *,
        target_ref: AttributeSubjectRef,
        definition_key: str,
        frame: int,
    ) -> int:
        """返回匹配记录的活动层数之和；无匹配记录时为 0。

        单条 stack 记录时即该记录的 `stack_count`；同类 multi 实例并存时
        求和，保证「叠加了几层」这一问法对两种表达都成立。
        """

        return sum(
            record.state.stack_count
            for record in self._records(
                target_ref=target_ref,
                definition_key=definition_key,
                frame=frame,
            )
        )


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
