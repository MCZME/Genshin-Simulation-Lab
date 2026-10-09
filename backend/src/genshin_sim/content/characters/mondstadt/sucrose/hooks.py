"""砂糖内容事件钩子：产球。

产球（维护者提供的角色产球表，实施规划 §6.5）：战技技能伤害命中产 4 风微粒
（100% 概率、判定冷却 0.4s = 24 帧）。概率 100% 无分布可选，不消费
``RandomSource``。触发面为战技命中的影响点（「元素战技（对己方非角色单位）」
行本期不实现，见 §6.3，不涉及产球）；触发影响点按伤害结果 ``request_id`` 内嵌
的 impact_key 匹配；判定冷却游标在 hook 实例，最近产球帧同步写入内容状态
``sucrose_last_particle_frame`` 供审计（0 表示尚未产球）。产球经
``ImpactKind.ENERGY`` 的 ``spawn_pickup`` 出口，归属宿主砂糖（风属性微粒）。

后续期在本文件续接 A1 / A4 天赋钩子（S5）与 C4 命中计数钩子（S8）。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_PARTICLE_COOLDOWN_FRAMES,
    SUCROSE_PARTICLE_COUNT,
    SUCROSE_PARTICLE_ELEMENT,
    SUCROSE_PARTICLE_SPAWN_IMPACT_KEY,
    SUCROSE_PARTICLE_TRAVEL_FRAMES,
    SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS,
    SUCROSE_STATE_LAST_PARTICLE_FRAME,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest

# 敌方目标判据按 entity_id 前缀区分（与奥黛塔产球 hook 同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class SucroseParticleHook:
    """产球：战技技能伤害命中产 4 风微粒，命中后 24 帧内不重复产球。"""

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"sucrose.particle:{owner_ref}"
        self.state_key = SUCROSE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 判定冷却游标在 hook 实例；内容状态字段随产出同步写入。
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
            key in request_id for key in SUCROSE_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < SUCROSE_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=SUCROSE_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": SUCROSE_PARTICLE_ELEMENT.value,
                            "count": SUCROSE_PARTICLE_COUNT,
                            "travel_frames": SUCROSE_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
            state_patches=(
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields={SUCROSE_STATE_LAST_PARTICLE_FRAME: frame},
                ),
            ),
        )
