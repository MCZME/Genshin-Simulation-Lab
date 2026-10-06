"""阿罗夏被动与命座的伤害修饰 provider（P5 充能效率增伤、P6 星超导增伤）。

数值一律取自资产效果行/倍率条目（组装期读入、由 provider 携带），内容代码
不留第二份常量（D-082：效果贡献由伤害修饰 provider 在结算期产出词条）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    ALYOSHA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
    ALYOSHA_TEAM_SCOPE,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    STAT_ENERGY_RECHARGE,
    AttributeSubjectRef,
    ProviderAttributeSubjectScope,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageAttributeRead,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
    STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
)

_SKILL_AND_BURST_ATTACK_TAGS = frozenset(
    {
        ALYOSHA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
        ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    }
)

# 星超导反应伤害标签（雷/冰两个方向变体）。P6 的「星超导反应伤害」只覆盖
# 星超导族，不含星扩散。
_STELLAR_CONDUCT_DAMAGE_TAGS = frozenset(
    {
        STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
        STELLAR_CONDUCT_ELECTRO_DAMAGE_TAG,
    }
)


def _require_non_negative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"{label} 必须是数字")
    number = float(value)
    if number < 0.0:
        raise ContentUnitValidationError(f"{label} 不能为负数")
    return number


class AlyoshaP5EnergyRechargeDamageBonusProvider:
    """P5 告别冬麦与残叶：基于阿罗夏充能效率提升 E/Q 伤害（词条通道）。

    资产文本「每 1% 元素充能效率使上述伤害提升 0.35%，至多提升至 70%」：
    增伤按**阿罗夏本人**的实时充能效率折算（provider owner 作用域读取），
    按伤害来源自筛为阿罗夏、按攻击标签筛元素战技/元素爆发；数值经
    ``DAMAGE_BONUS_ADD`` 词条进入伤害加成加算区。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        er_step: float,
        bonus_per_step: float,
        cap: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("P5 充能效率增伤 owner_ref 必须是非空字符串")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._er_step = _require_non_negative(er_step, "P5 充能效率步长")
        self._bonus_per_step = _require_non_negative(bonus_per_step, "P5 每步增伤")
        self._cap = _require_non_negative(cap, "P5 增伤上限")
        if self._er_step <= 0.0:
            raise ContentUnitValidationError("P5 充能效率步长必须为正数")
        self._provider_key = f"{source_key}.er_damage_bonus:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            reads=(
                DamageAttributeRead(
                    STAT_ENERGY_RECHARGE,
                    ProviderAttributeSubjectScope.PROVIDER_OWNER,
                ),
            ),
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        request = query.request
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag not in _SKILL_AND_BURST_ATTACK_TAGS:
            return ()
        er = float(
            scope.resolve_for_provider(
                STAT_ENERGY_RECHARGE,
                ProviderAttributeSubjectScope.PROVIDER_OWNER,
            ).final_value
        )
        value = min(er / self._er_step * self._bonus_per_step, self._cap)
        if value <= 0.0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )


class AlyoshaP6StellarConductBonusProvider:
    """P6 星赴险域：猎者之准使场上角色星超导反应伤害按层提升（词条通道）。

    资产文本「激活弋猎印记时获得的猎者之准，额外使当前场上角色的星超导反应
    伤害提升 20%（随猎者之准层数叠加，C6 下至多 40%）」：门控 = 猎者之准
    在场（``ACTIVE_CHARACTER`` 位置级主体上的层数，经目标状态只读端口读取，
    不接触 Buff 定义细节以外的运行态）；星超导反应伤害仅在极星辉域会话内
    存在，辉映门控由伤害标签天然承载（辉映·星超导 Buff 由星超导协调自动
    授予，不经内容侧发放）。数值经 ``STELLAR_REACTION_BONUS_ADD`` 词条进入
    星烁反应增伤槽位（多个来源加算）。

    「当前场上角色」口径：层数读取在位置级主体上进行（全队持有/前台生效由
    Buff 投影语义承担），本 provider 不再按伤害来源筛攻击者——星超导伤害在
    仿真中由前台角色攻击与轰霆猎场 tick 触发，位置级门控与文本口径的偏差
    仅剩「阿罗夏后台时其 tick 触发的星超导也吃到增伤」一种，随创建实体归属
    口径一并记录。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        bonus_per_stack: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("P6 星超导增伤 owner_ref 必须是非空字符串")
        self._bonus_per_stack = _require_non_negative(bonus_per_stack, "P6 星超导增伤")
        if self._bonus_per_stack <= 0.0:
            raise ContentUnitValidationError("P6 星超导增伤必须为正数")
        self._team_subject_ref = AttributeSubjectRef.active_character(ALYOSHA_TEAM_SCOPE)
        self._provider_key = f"{source_key}.stellar_conduct_bonus"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=AttributeSubjectRef.character(owner_ref),
            display_name=display_name,
        )

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配阶段原位绑定目标状态只读端口（读猎者之准当前层数）。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.main_attack_tag not in _STELLAR_CONDUCT_DAMAGE_TAGS:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        stacks = port.active_stack_count(
            target_ref=self._team_subject_ref,
            definition_key=ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
            frame=request.frame,
        )
        value = self._bonus_per_stack * stacks
        if value <= 0.0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=value,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )
