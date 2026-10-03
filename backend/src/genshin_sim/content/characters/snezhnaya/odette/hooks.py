"""奥黛塔内容事件钩子：产球。

产球（维护者提供的角色产球表）：战技技能伤害命中或破晓终奏持续命中产
5 冰微粒（100% 概率、共用 12s 判定冷却），触发面与命中表「元素战技掉球」
附加标签的命中一致（E 初始段 + 破晓终奏持续三段；Q 与舞步不产球）。
触发影响点按伤害结果 ``request_id`` 内嵌的 impact_key 匹配；冷却游标在
hook 实例，最近产球帧同步写入内容状态 ``odette_last_particle_frame`` 供
审计（0 表示尚未产球）。产球经 ``ImpactKind.ENERGY`` 的 ``spawn_pickup``
出口，归属宿主奥黛塔（冰属性微粒）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_PARTICLE_COOLDOWN_FRAMES,
    ODETTE_PARTICLE_COUNT,
    ODETTE_PARTICLE_ELEMENT,
    ODETTE_PARTICLE_SPAWN_IMPACT_KEY,
    ODETTE_PARTICLE_TRAVEL_FRAMES,
    ODETTE_PARTICLE_TRIGGER_IMPACT_KEYS,
    ODETTE_STATE_LAST_PARTICLE_FRAME,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest

# 敌方目标判据按 entity_id 前缀区分（与西风系列武器钩子同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class OdetteParticleHook:
    """产球：战技技能伤害与破晓终奏持续命中产 5 冰微粒，共用 12s 判定冷却。"""

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"odette.particle:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 冷却游标在 hook 实例；内容状态字段随产出同步写入。
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        request_id = getattr(result, "request_id", None)
        if not isinstance(request_id, str) or not any(
            key in request_id for key in ODETTE_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < ODETTE_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=ODETTE_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": ODETTE_PARTICLE_ELEMENT.value,
                            "count": ODETTE_PARTICLE_COUNT,
                            "travel_frames": ODETTE_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
            state_patches=(
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields={ODETTE_STATE_LAST_PARTICLE_FRAME: frame},
                ),
            ),
        )
