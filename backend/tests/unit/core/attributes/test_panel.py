from __future__ import annotations

from typing import Any, cast

from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    AttributeKey,
    AttributeQuery,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.attributes.panel import (
    AttributePanelSynchronizer,
    attributes_provider_dict,
)
from genshin_sim.core.attributes.resolver import AttributeResolver
from genshin_sim.core.events import EventType
from genshin_sim.core.simulation.context import SimulationContext

CHARACTER = AttributeSubjectRef.character("character:slot_1")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "config:test")


class GatedAtkProvider:
    """按帧改变攻击加成的动态修饰器，模拟 Buff 生效/变化。"""

    def __init__(self) -> None:
        self.provider_spec = ModifierProviderSpec(
            provider_key="provider:gated_atk",
            writes=frozenset({STAT_ATK_TOTAL}),
        )

    def contribute(self, query: AttributeQuery, session: object) -> tuple[ModifierTerm, ...]:
        del session
        if query.subject_ref != CHARACTER:
            return ()
        if query.frame < 5:
            return ()
        value = 300.0 if query.frame < 10 else 400.0
        return (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.FLAT_ADD,
                value=value,
                provider_key="provider:gated_atk",
                source_ref=CONFIG_SOURCE,
            ),
        )


def _resolver(
    *,
    base_value: float,
    providers: tuple[Any, ...],
) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    CHARACTER,
                    BaseAttributeContribution(STAT_ATK_BASE, base_value, CONFIG_SOURCE),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex(providers, registry=registry),
    )


def test_attributes_provider_dict_serializes_panel_with_terms():
    resolver = _resolver(base_value=1000.0, providers=(GatedAtkProvider(),))

    provider = attributes_provider_dict(resolver, (CHARACTER,), frame=5)

    assert provider["frame"] == 5
    subjects = cast(dict[str, object], provider["subjects"])
    panel = cast(dict[str, object], subjects["character:slot_1"])
    atk_total = cast(dict[str, object], panel["stat.atk.total"])
    assert atk_total["value"] == 1300.0
    terms = cast(tuple[dict[str, object], ...], atk_total["applied_terms"])
    assert len(terms) == 1
    assert terms[0]["provider_key"] == "provider:gated_atk"
    assert terms[0]["target_key"] == "stat.atk.total"
    assert terms[0]["source_ref"] == {
        "kind": "config",
        "source_key": "config:test",
        "instance_id": None,
    }


def test_panel_synchronizer_publishes_changed_fields_only():
    resolver = _resolver(base_value=1000.0, providers=(GatedAtkProvider(),))
    synchronizer = AttributePanelSynchronizer(resolver, (CHARACTER,))
    synchronizer.capture_baseline(0)
    context = SimulationContext()

    synchronizer.update_frame(context, 1)
    assert not any(
        event.event_type is EventType.ATTRIBUTE_PANEL_CHANGED
        for event in context.events.frame_events
    )

    synchronizer.update_frame(context, 5)
    changed = [
        event
        for event in context.events.frame_events
        if event.event_type is EventType.ATTRIBUTE_PANEL_CHANGED
    ]
    assert len(changed) == 1
    payload = changed[0].payload.to_dict()
    assert payload["frame"] == 5
    assert payload["subject_ref"] == {"kind": "character", "entity_id": "character:slot_1"}
    changes = cast(tuple[dict[str, object], ...], payload["changes"])
    assert len(changes) == 1
    assert changes[0]["attribute_key"] == "stat.atk.total"
    assert changes[0]["before_value"] == 1000.0
    assert changes[0]["after_value"] == 1300.0
    assert len(cast(tuple[object, ...], changes[0]["after_terms"])) == 1

    synchronizer.update_frame(context, 6)
    changed = [
        event
        for event in context.events.frame_events
        if event.event_type is EventType.ATTRIBUTE_PANEL_CHANGED
    ]
    assert len(changed) == 1

    synchronizer.update_frame(context, 10)
    changed = [
        event
        for event in context.events.frame_events
        if event.event_type is EventType.ATTRIBUTE_PANEL_CHANGED
    ]
    assert len(changed) == 2
    changes = cast(
        tuple[dict[str, object], ...],
        changed[1].payload.to_dict()["changes"],
    )
    assert changes[0]["before_value"] == 1300.0
    assert changes[0]["after_value"] == 1400.0


def test_panel_synchronizer_skips_unchanged_keys():
    resolver = _resolver(base_value=1000.0, providers=())
    synchronizer = AttributePanelSynchronizer(
        resolver,
        (CHARACTER,),
        keys=(AttributeKey("stat.atk.total"),),
    )
    synchronizer.capture_baseline(0)
    context = SimulationContext()

    synchronizer.update_frame(context, 20)

    assert not any(
        event.event_type is EventType.ATTRIBUTE_PANEL_CHANGED
        for event in context.events.frame_events
    )
