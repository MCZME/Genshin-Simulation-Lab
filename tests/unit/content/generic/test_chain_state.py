from __future__ import annotations

from genshin_sim.content.generic.chain_state import chain_state_schema


def test_chain_state_schema_has_defaults():
    schema = chain_state_schema("character:slot_1")

    assert schema.defaults() == {
        "chain_last_action_key": "",
        "chain_last_start_frame": 0,
    }
