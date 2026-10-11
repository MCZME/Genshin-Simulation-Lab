"""苍古自由之誓被动的伤害修饰：常驻伤害提高与抗争之歌的普/重/落伤害提高。"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.team import PLAYER_TEAM_SCOPE
from genshin_sim.content.weapons.sword.freedom_sworn.data import (
    is_normal_charged_plunging_tag,
)
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


class FreedomSwornDamageBonusProvider:
    """「抗争的践行之歌」常驻段：装备者造成的伤害提高。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        damage_bonus: float,
        source_key: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("伤害提高 provider owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("伤害提高 provider 必须绑定正整数队伍槽位")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._damage_bonus = float(damage_bonus)
        self._provider_key = f"{source_key}.damage_bonus"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name="苍古自由之誓·伤害提高",
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.formula_key != FORMULA_KEY_GENERAL:
            return ()
        if request.source_ref != self._owner_ref:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._damage_bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=("freedom_sworn",),
            ),
        )


class FreedomSwornSongAttackTagProvider:
    """抗争之歌生效期间，队伍内角色普攻/重击/下落攻击造成的伤害提高。"""

    def __init__(
        self,
        *,
        slot: int,
        definition_key: str,
        bonus: float,
        source_key: str,
    ) -> None:
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("抗争之歌 provider 必须绑定正整数队伍槽位")
        self._definition_key = definition_key
        self._bonus = float(bonus)
        self._team_subject_ref = AttributeSubjectRef.team(PLAYER_TEAM_SCOPE)
        self._provider_key = f"{source_key}.song_attack_tag_bonus"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._team_subject_ref,
            display_name="苍古自由之誓·抗争之歌",
        )
        self._target_status_port: TargetBuffPresenceReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        target_status_port: TargetBuffPresenceReadPort,
    ) -> None:
        """装配期注入目标状态只读端口；未绑定时不贡献。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.formula_key != FORMULA_KEY_GENERAL:
            return ()
        if not is_normal_charged_plunging_tag(request.main_attack_tag):
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=self._team_subject_ref,
            definition_key=self._definition_key,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=("freedom_sworn_song",),
            ),
        )
