"""月兆领域的伤害修饰 provider。

非月兆角色的月曜增伤按决策记录 D-082「槽位账单是伤害公式的唯一修饰通道」的要求，
以 ``lunar_reaction_bonus_add`` 词条进入月曜公式位置 5（反应加成）的槽位账单，
不再由 ``ElementalSettlementCoordinator`` 算好后写进 ``LunarReactionDamageInput`` 的
强类型字段。词条值等于该帧的生效增伤（小数倍率），因此迁移前后数值落在同一个
``反应加成基线 + Σ 词条`` 括号内，逐组分等价。
"""

from __future__ import annotations

from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
    DamageQuery,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.moonsign.errors import MoonsignValidationError
from genshin_sim.core.systems.moonsign.ports import LunarDamageBonusPort

MOONSIGN_LUNAR_BONUS_PROVIDER_KEY = "moonsign.lunar_reaction_bonus"
MOONSIGN_LUNAR_BONUS_SOURCE_KEY = "moonsign:lunar_bonus"
MOONSIGN_LUNAR_BONUS_AUDIT_TAG = "moonsign.lunar_bonus"


class MoonsignLunarBonusProvider:
    """把当前生效的非月兆月曜增伤写成月曜公式的反应加成词条。

    ``lunar_reaction_bonus_add`` 只属于月曜公式的位置 5；若不加公式过滤，provider 会在
    通用直伤、剧变与星烁查询上成交，被 ``validate_formula_modifier_stages`` 硬拒绝并让
    整次结算失败。因此按 ``FORMULA_KEY_LUNAR_REACTION`` 自筛（与元素共鸣的条件
    provider 同一处理方式）。

    未绑定运行端口时不生效，因此装配期早于绑定发生的伤害查询不受影响。
    """

    provider_spec = DamageModifierProviderSpec(
        provider_key=MOONSIGN_LUNAR_BONUS_PROVIDER_KEY,
        writes=frozenset({DamageModifierStage.LUNAR_REACTION_BONUS_ADD}),
        display_name="月兆月曜增伤",
    )

    def __init__(self) -> None:
        self._bonus_port: LunarDamageBonusPort | None = None

    def bind_runtime_ports(self, *, bonus_port: LunarDamageBonusPort) -> None:
        """绑定月兆运行态只读端口；只发生在装配期。"""

        self._bonus_port = bonus_port

    def contribute(
        self,
        query: DamageQuery,
        session: DamageResolutionSession,
    ) -> tuple[DamageModifierTerm, ...]:
        """按查询帧读取当前增伤，产出位置 5 的单个修饰项。"""

        del session
        if self._bonus_port is None:
            return ()
        request = query.request
        if request.formula_key is not FORMULA_KEY_LUNAR_REACTION:
            return ()
        value = self._bonus_port.lunar_reaction_bonus(request.frame)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise MoonsignValidationError("月曜增伤端口返回了非数字")
        if value <= 0:
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.LUNAR_REACTION_BONUS_ADD,
                value=float(value),
                provider_key=self.provider_spec.provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.SYSTEM,
                    MOONSIGN_LUNAR_BONUS_SOURCE_KEY,
                ),
                audit_tags=(MOONSIGN_LUNAR_BONUS_AUDIT_TAG,),
            ),
        )
