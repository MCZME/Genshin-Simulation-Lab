from __future__ import annotations

from collections.abc import Mapping

import pytest

from genshin_sim.content.generic.predicates import (
    InvalidPredicateParameterError,
    PredicateContext,
    PredicateError,
    all_of,
    any_of,
    field_equals,
    has_buff,
    hp_ratio_above,
    hp_ratio_below,
    is_active_character,
    negate,
    stacks_above,
    stacks_at_least,
)
from genshin_sim.core.contracts.json import JSONValue


class FakeTeamState:
    active_slot = 2


class FakeSpaceRuntime:
    team_state = FakeTeamState()


class FakeSimulation:
    space_runtime = FakeSpaceRuntime()


def _context(
    *,
    state: Mapping[str, JSONValue] | None = None,
    owner_slot: int | None = None,
    simulation: object | None = None,
    buff_lookup=None,
) -> PredicateContext:
    return PredicateContext(
        frame=1,
        owner_ref="character:slot:1",
        state=state or {},
        owner_slot=owner_slot,
        simulation=simulation,
        buff_lookup=buff_lookup,
    )


def test_stacks_predicates_read_content_state():
    context = _context(state={"stacks": 3})

    assert stacks_at_least("stacks", 3)(context) is True
    assert stacks_at_least("stacks", 4)(context) is False
    assert stacks_above("stacks", 3)(context) is False
    assert stacks_above("stacks", 2)(context) is True


def test_stacks_predicate_reports_missing_field():
    with pytest.raises(PredicateError, match="缺失"):
        stacks_at_least("stacks", 1)(_context())


def test_field_equals_predicate():
    context = _context(state={"mode": "ousia"})

    assert field_equals("mode", "ousia")(context) is True
    assert field_equals("mode", "pneuma")(context) is False


def test_hp_ratio_predicates():
    context = _context(state={"hp_ratio": 0.4})

    assert hp_ratio_above(0.4)(context) is True
    assert hp_ratio_above(0.5)(context) is False
    assert hp_ratio_below(0.5)(context) is True
    assert hp_ratio_below(0.4)(context) is False


def test_hp_ratio_predicate_rejects_out_of_range_value():
    with pytest.raises(PredicateError, match="超出"):
        hp_ratio_above(0.5)(_context(state={"hp_ratio": 1.2}))


def test_hp_ratio_factory_rejects_invalid_parameter():
    with pytest.raises(InvalidPredicateParameterError, match="0 到 1"):
        hp_ratio_above(1.5)


def test_is_active_character_compares_owner_slot_with_team_state():
    assert is_active_character()(_context(owner_slot=2, simulation=FakeSimulation())) is True
    assert is_active_character()(_context(owner_slot=1, simulation=FakeSimulation())) is False
    assert is_active_character()(_context(owner_slot=None, simulation=FakeSimulation())) is False


def test_is_active_character_requires_space_runtime():
    with pytest.raises(PredicateError, match="space_runtime"):
        is_active_character()(_context(owner_slot=1, simulation=object()))


def test_has_buff_uses_injected_lookup_port():
    active_buffs = {"buff.test.active"}

    def lookup(buff_key: str) -> bool:
        return buff_key in active_buffs

    context = _context(buff_lookup=lookup)
    assert has_buff("buff.test.active")(context) is True
    assert has_buff("buff.test.inactive")(context) is False


def test_has_buff_requires_lookup_port():
    with pytest.raises(PredicateError, match="buff 查询端口"):
        has_buff("buff.test")(_context())


def test_combinators():
    context = _context(state={"stacks": 2, "hp_ratio": 0.8})

    assert all_of(stacks_at_least("stacks", 2), hp_ratio_above(0.5))(context) is True
    assert all_of(stacks_at_least("stacks", 3), hp_ratio_above(0.5))(context) is False
    assert any_of(stacks_at_least("stacks", 3), hp_ratio_above(0.5))(context) is True
    assert negate(stacks_at_least("stacks", 3))(context) is True


def test_combinator_rejects_empty():
    with pytest.raises(InvalidPredicateParameterError, match="至少"):
        all_of()
