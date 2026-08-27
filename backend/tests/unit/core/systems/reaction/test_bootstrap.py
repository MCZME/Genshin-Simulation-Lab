from genshin_sim.core.systems.reaction import create_default_reaction_bootstrap
from genshin_sim.core.systems.reaction.mechanics.burning import (
    BURNING_DAMAGE_PROFILE_KEY,
    BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY,
    burning_damage_profile,
    burning_gate_definitions,
    burning_pyro_aura_application_profile,
)

EXPECTED_REACTION_KEYS = {
    "reaction.aggravate",
    "reaction.bloom",
    "reaction.bloom_explosion",
    "reaction.burgeon",
    "reaction.burning",
    "reaction.crystallize",
    "reaction.electro_charged",
    "reaction.frozen",
    "reaction.hyperbloom",
    "reaction.lunar_bloom",
    "reaction.lunar_crystallize",
    "reaction.lunar_electro_charged",
    "reaction.melt",
    "reaction.overloaded",
    "reaction.quicken",
    "reaction.shattered",
    "reaction.spread",
    "reaction.superconduct",
    "reaction.swirl",
    "reaction.vaporize",
}

EXPECTED_DAMAGE_GATE_KEYS = {
    "reaction_gate.bloom_family.damage",
    "reaction_gate.burning.damage",
    "reaction_gate.electro_charged.damage",
    "reaction_gate.lunar_electro_charged.damage",
    "reaction_gate.overloaded.damage",
    "reaction_gate.shattered.damage",
    "reaction_gate.superconduct.damage",
    "reaction_gate.swirl.cryo.damage",
    "reaction_gate.swirl.electro.damage",
    "reaction_gate.swirl.hydro.damage",
    "reaction_gate.swirl.pyro.damage",
}

EXPECTED_ESTABLISHMENT_GATE_KEYS = {"reaction_gate.crystallize.establishment"}


def test_default_bootstrap_registers_each_current_definition_once() -> None:
    bootstrap = create_default_reaction_bootstrap()

    assert {item.reaction_key for item in bootstrap.reaction_registry.definitions} == (
        EXPECTED_REACTION_KEYS
    )
    assert {item.gate_definition_key for item in bootstrap.damage_gate_definitions} == (
        EXPECTED_DAMAGE_GATE_KEYS
    )
    assert {
        item.gate_definition_key for item in bootstrap.establishment_gate_definitions
    } == EXPECTED_ESTABLISHMENT_GATE_KEYS


def test_default_bootstrap_creates_runtime_with_the_same_gate_surface() -> None:
    bootstrap = create_default_reaction_bootstrap()
    runtime = bootstrap.create_runtime()

    for gate_key in EXPECTED_DAMAGE_GATE_KEYS:
        assert runtime.gate_definition(gate_key).gate_definition_key == gate_key
    for gate_key in EXPECTED_ESTABLISHMENT_GATE_KEYS:
        assert runtime.establishment_gate_definition(gate_key).gate_definition_key == gate_key


def test_burning_specific_profiles_and_gate_registered_in_default_bootstrap() -> None:
    bootstrap = create_default_reaction_bootstrap()

    assert burning_gate_definitions()[0] in bootstrap.damage_gate_definitions
    assert burning_damage_profile().profile_key == BURNING_DAMAGE_PROFILE_KEY
    assert (
        burning_pyro_aura_application_profile().profile_key
        == BURNING_PYRO_AURA_APPLICATION_PROFILE_KEY
    )
