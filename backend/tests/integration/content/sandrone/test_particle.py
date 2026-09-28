"""桑多涅产球的纵向集成：射线命中产冰微粒、共用判定冷却与能量结算。"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_PARTICLE_TRAVEL_FRAMES,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers

SANDRONE_REF = AttributeSubjectRef.character("character:slot_1")


def _hold_trace(press_frame: int, release_frame: int) -> list[dict[str, object]]:
    return [
        {"frame": press_frame, "events": [{"key": "mouse.left", "phase": "press"}]},
        {"frame": release_frame, "events": [{"key": "mouse.left", "phase": "release"}]},
    ]


def test_ray_hits_spawn_cryo_particle_with_shared_cooldown(sandrone_assembled):
    # 产球：射线按法洁欧节奏连续命中（间隔 60，均在 150F 共用冷却内），
    # 仅首个命中产 1 冰微粒；产球经统一意图队列在命中帧入队。
    assembled = sandrone_assembled(
        max_frames=380,
        payload=sandrone_helpers.charged_line_payload(380, 2, 376),
    )
    spawn_events: list = []
    assembled.context.events.subscribe(EventType.ENERGY_PICKUP_SPAWNED, spawn_events.append)

    assembled.simulator.run()

    ray_frames = sandrone_helpers.charged_ray_frames(2, 3)
    records = [event.payload.record for event in spawn_events]
    assert [
        (record.created_frame, record.pickup_kind.value, record.element.value, record.count)
        for record in records
    ] == [(ray_frames[0], "particle", "cryo", 1)]
    # 微粒按载体飞行延迟结算：同元素微粒场上 3 点（充能效率 100%）。终值取
    # 下界——重击标签伤害还会触发通用回能，可能额外恢复。
    assert records[0].settle_frame == ray_frames[0] + SANDRONE_PARTICLE_TRAVEL_FRAMES
    assert assembled.energy_store.current_energy(SANDRONE_REF) >= 3.0
