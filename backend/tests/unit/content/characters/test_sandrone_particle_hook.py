"""产球 hook 的单元测试：触发影响点、共用判定冷却与冰微粒载荷。"""

from __future__ import annotations

from typing import cast

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_STATE_LAST_PARTICLE_FRAME,
    SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_PARTICLE_SPAWN_IMPACT_KEY,
    SANDRONE_PARTICLE_TRAVEL_FRAMES,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import SandroneParticleHook
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.events import EmptyPayload, EventType, GameEvent
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from tests.helpers.events import make_damage_resolved_event

SLOT = 1
OWNER_REF = "character:slot_1"
RAY_REQUEST_ID = (
    f"sandrone.fageou:{OWNER_REF}:{SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY}:131:1:target:target_1:0"
)
EXTRA_REQUEST_ID = (
    f"sandrone.fageou:{OWNER_REF}:{SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY}:131:2"
    ":target:target_1:0"
)
PRISM_REQUEST_ID = f"action:9:{SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY}:target:target_1:0"
SWEEP_REQUEST_ID = (
    f"sandrone.fageou:{OWNER_REF}:character.sandrone.charged_attack.sweep:59:1:target:target_1:0"
)


def _hook() -> SandroneParticleHook:
    return SandroneParticleHook(owner_ref=OWNER_REF, slot=SLOT)


def _hit(request_id: str, *, frame: int = 100, source_key: str = OWNER_REF) -> GameEvent:
    event = make_damage_resolved_event(
        frame,
        request_id,
        source_key=source_key,
        main_attack_tag="重击",
    )
    return cast(GameEvent, event)


def _apply_patches(result, state: dict[str, object]) -> None:
    for patch in result.state_patches:
        assert isinstance(patch, StatePatchRequest)
        state.update(patch.fields)


def test_ray_hit_spawns_one_cryo_particle():
    hook = _hook()
    state: dict[str, object] = {}

    result = hook.handle(_hit(RAY_REQUEST_ID, frame=100), None)

    assert len(result.impact_requests) == 1
    request = cast(ImpactRequest, result.impact_requests[0])
    assert request.kind is ImpactKind.ENERGY
    assert request.impact_key == SANDRONE_PARTICLE_SPAWN_IMPACT_KEY
    assert request.owner_slot == SLOT
    energy = cast(dict, request.params["energy"])
    assert energy["schema_version"] == 1
    assert energy["operation"] == "spawn_pickup"
    assert energy["pickup_kind"] == "particle"
    assert energy["element"] == "cryo"
    assert energy["count"] == 1
    assert energy["travel_frames"] == SANDRONE_PARTICLE_TRAVEL_FRAMES
    _apply_patches(result, state)
    assert state[FAGEOU_STATE_LAST_PARTICLE_FRAME] == 100


def test_prism_and_extra_segment_hits_are_in_trigger_vocabulary():
    prism_result = _hook().handle(_hit(PRISM_REQUEST_ID), None)
    extra_result = _hook().handle(_hit(EXTRA_REQUEST_ID), None)

    assert len(prism_result.impact_requests) == 1
    assert len(extra_result.impact_requests) == 1


def test_same_frame_ray_and_extra_segment_spawn_only_one_particle():
    # 射线与 C6 追加段同帧命中：冷却游标即时去重，只产 1 粒（状态字段下一
    # 轮才落地，不能依赖它判重）。
    hook = _hook()

    first = hook.handle(_hit(RAY_REQUEST_ID, frame=131), None)
    second = hook.handle(_hit(EXTRA_REQUEST_ID, frame=131), None)

    assert len(first.impact_requests) == 1
    assert second.impact_requests == ()
    assert second.state_patches == ()


def test_shared_cooldown_suppresses_inside_window():
    hook = _hook()

    assert len(hook.handle(_hit(RAY_REQUEST_ID, frame=100), None).impact_requests) == 1
    suppressed = hook.handle(_hit(PRISM_REQUEST_ID, frame=110), None)

    assert suppressed.impact_requests == ()
    assert suppressed.state_patches == ()


def test_cooldown_elapses_and_spawns_again():
    hook = _hook()

    assert len(hook.handle(_hit(RAY_REQUEST_ID, frame=100), None).impact_requests) == 1
    later = hook.handle(_hit(RAY_REQUEST_ID, frame=250), None)

    assert len(later.impact_requests) == 1


def test_non_trigger_damage_does_not_spawn():
    result = _hook().handle(_hit(SWEEP_REQUEST_ID), None)

    assert result.impact_requests == ()
    assert result.state_patches == ()


def test_damage_from_other_sources_is_ignored():
    result = _hook().handle(_hit(RAY_REQUEST_ID, source_key="character:slot_2"), None)

    assert result.impact_requests == ()
    assert result.state_patches == ()


def test_non_damage_events_are_ignored():
    result = _hook().handle(
        GameEvent(EventType.SIMULATION_STARTED, frame=5, payload=EmptyPayload()),
        None,
    )

    assert result.impact_requests == ()
    assert result.state_patches == ()
