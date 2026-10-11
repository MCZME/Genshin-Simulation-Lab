"""旅行剑被动的事件钩子：获得元素微粒或元素晶球时按最大生命比例恢复生命。

订阅 ``ENERGY_PICKUP_SETTLED`` 事实，只读取事实、只产出下一轮结算要消费的
``ImpactRequest``，不直接写生命状态。「获得」判定：结算结果的 recipients 中
装备者槽位的能量结算状态为 ``applied``（实际获得了能量）；``capped`` 表示
能量已满没有获得，不触发治疗。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.sword.travelers_handy_sword.data import (
    TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.energy import EnergyPickupSettlementResult, EnergyRecipientStatus


class JourneyPickupHealHook:
    """装备者获得元素微粒或元素晶球时，按装备者最大生命值比例恢复生命。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        heal_ratio: float,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("旅程 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("旅程 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("旅程必须绑定正整数队伍槽位")
        if isinstance(heal_ratio, bool) or not isinstance(heal_ratio, int | float):
            raise ContentUnitValidationError("旅程治疗比例必须是数字")
        if not 0.0 < float(heal_ratio) <= 1.0:
            raise ContentUnitValidationError("旅程治疗比例必须在 0 到 1 之间")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._slot = slot
        self._heal_ratio = float(heal_ratio)
        self.hook_key = f"{TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY}:{owner_ref}"
        self.state_key = handler_key
        self.subscriptions = ("ENERGY_PICKUP_SETTLED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if not isinstance(result, EnergyPickupSettlementResult):
            return HookResult()
        if not self._owner_gained_energy(result):
            return HookResult()
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.HEAL,
                    impact_key=TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    target_refs=(self._owner_ref,),
                    params={
                        "heal": {
                            "healing_id": TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY,
                            "scaling_terms": (
                                {
                                    "component_key": "pickup_heal",
                                    "attribute_key": "stat.hp.max",
                                    "coefficient": self._heal_ratio,
                                },
                            ),
                            "flat_healing": 0.0,
                            "source_context": {
                                "kind": "content",
                                "source_key": self._handler_key,
                            },
                            "tags": (self._handler_key,),
                        },
                    },
                ),
            )
        )

    def _owner_gained_energy(self, result: EnergyPickupSettlementResult) -> bool:
        return any(
            recipient.slot == self._slot and recipient.status is EnergyRecipientStatus.APPLIED
            for recipient in result.recipients
        )
