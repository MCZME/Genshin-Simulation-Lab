"""芭芭拉元素爆发的纵向集成：治疗、能量消耗与能量门槛。"""

from __future__ import annotations

import pytest

from genshin_sim.content import (
    BARBARA_ELEMENTAL_BURST_ACTION_KEY,
    BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.cooldown import CooldownKey, CooldownSubjectRef
from genshin_sim.core.systems.energy.models import RestoreEnergyRequest


def test_barbara_elemental_burst_heals_team_and_spends_energy(
    barbara_assembled,
):
    assembled = barbara_assembled(input_key="keyboard.q", max_frames=90)
    assembled.energy_runtime.restore(
        RestoreEnergyRequest(
            change_id="test:burst:full",
            frame=0,
            target_ref=AttributeSubjectRef.character("character:slot_1"),
            amount=80.0,
        )
    )

    result = assembled.simulator.run()

    assert result.end_frame >= 80
    burst_heals = [
        record
        for record in assembled.impact_request_dispatcher.healing_records
        if record.impact_request.impact_key == BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY
    ]
    assert len(burst_heals) == 1
    assert burst_heals[0].records[0].result.final_healing == pytest.approx(3454.2819)
    energy_ref = AttributeSubjectRef.character("character:slot_1")
    assert assembled.energy_runtime.get_current_energy(energy_ref) == pytest.approx(0.0)
    cooldown_key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_burst",
    )
    assert assembled.cooldown_runtime.store.get_record(cooldown_key).available_charges == 0


def test_barbara_elemental_burst_rejected_without_energy(barbara_assembled):
    assembled = barbara_assembled(input_key="keyboard.q", max_frames=10)

    assembled.simulator.run()

    assert not any(
        instance.action_key == BARBARA_ELEMENTAL_BURST_ACTION_KEY
        for instance in assembled.action_manager.instances
    )
