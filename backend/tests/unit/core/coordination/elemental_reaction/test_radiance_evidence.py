# 单一关注点：星烁辉映证据窄端口——变体优先级、载荷读取与缺席语义。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.elemental_reaction.radiance_evidence import (
    StellarRadianceEvidenceReader,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    plan_radiance_buff_requests,
    stellar_radiance_buff_definition,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    plan_stellar_swirl_radiance_buff_requests,
    stellar_swirl_radiance_buff_definition,
)
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.buff import (
    BuffDefinitionRegistry,
    BuffResolver,
    BuffRuntime,
    BuffStore,
)
from genshin_sim.core.systems.reaction.radiance import (
    RadianceEvidence,
    RadianceVariant,
)
from genshin_sim.core.systems.reaction.states import STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES

CHARACTER = AttributeSubjectRef.character("character:test")
OWNER_REF = CHARACTER.entity_id
OCCURRENCE = "interaction:1:occurrence:0"
# 领域到期 + 辉映延续窗口之后，两种辉映都应失效。
EXPIRED_FRAME = STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES + 120


def _build_runtime() -> tuple[BuffRuntime, StellarRadianceEvidenceReader]:
    runtime = BuffRuntime(
        definition_registry=BuffDefinitionRegistry(
            (stellar_radiance_buff_definition(), stellar_swirl_radiance_buff_definition())
        ),
        resolver=BuffResolver(),
        buff_store=BuffStore(),
        event_engine=EventEngine(),
    )
    return runtime, StellarRadianceEvidenceReader(runtime.reader)


def _apply_conduct(runtime: BuffRuntime, *, settled_stacks: int) -> None:
    for request in plan_radiance_buff_requests(
        frame=0,
        occurrence_ref=OCCURRENCE,
        character_refs=(CHARACTER,),
        settled_stacks=settled_stacks,
        field_expires_at_frame=STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    ):
        runtime.apply(request)


def _apply_swirl(runtime: BuffRuntime) -> None:
    for request in plan_stellar_swirl_radiance_buff_requests(
        frame=0,
        occurrence_ref=OCCURRENCE,
        character_refs=(CHARACTER,),
    ):
        runtime.apply(request)


def test_resolve_returns_none_and_zero_multiplier_without_radiance() -> None:
    _, reader = _build_runtime()

    assert reader.resolve(owner_ref=OWNER_REF, frame=10) is None
    assert (
        reader.variant_multiplier(owner_ref=OWNER_REF, variant=RadianceVariant.CONDUCT, frame=10)
        == 0.0
    )
    assert (
        reader.variant_multiplier(owner_ref=OWNER_REF, variant=RadianceVariant.SWIRL, frame=10)
        == 0.0
    )


def test_resolve_reads_conduct_payload_value() -> None:
    runtime, reader = _build_runtime()
    _apply_conduct(runtime, settled_stacks=3)

    evidence = reader.resolve(owner_ref=OWNER_REF, frame=10)
    assert evidence is not None and evidence.variant is RadianceVariant.CONDUCT
    assert evidence.direct_base_multiplier == pytest.approx(1.55)
    assert (
        reader.variant_multiplier(owner_ref=OWNER_REF, variant=RadianceVariant.SWIRL, frame=10)
        == 0.0
    )


def test_resolve_reads_swirl_payload_value() -> None:
    runtime, reader = _build_runtime()
    _apply_swirl(runtime)

    evidence = reader.resolve(owner_ref=OWNER_REF, frame=10)
    assert evidence == RadianceEvidence(RadianceVariant.SWIRL, 1.0)
    assert (
        reader.variant_multiplier(owner_ref=OWNER_REF, variant=RadianceVariant.SWIRL, frame=10)
        == 1.0
    )
    assert (
        reader.variant_multiplier(owner_ref=OWNER_REF, variant=RadianceVariant.CONDUCT, frame=10)
        == 0.0
    )


def test_resolve_prefers_conduct_when_both_radiance_present() -> None:
    runtime, reader = _build_runtime()
    _apply_swirl(runtime)
    _apply_conduct(runtime, settled_stacks=3)

    evidence = reader.resolve(owner_ref=OWNER_REF, frame=10)
    assert evidence is not None and evidence.variant is RadianceVariant.CONDUCT
    assert evidence.direct_base_multiplier == pytest.approx(1.55)


def test_resolve_returns_none_after_radiance_expires() -> None:
    runtime, reader = _build_runtime()
    _apply_swirl(runtime)
    _apply_conduct(runtime, settled_stacks=3)

    assert reader.resolve(owner_ref=OWNER_REF, frame=10) is not None
    assert reader.resolve(owner_ref=OWNER_REF, frame=EXPIRED_FRAME) is None
    assert (
        reader.variant_multiplier(
            owner_ref=OWNER_REF, variant=RadianceVariant.CONDUCT, frame=EXPIRED_FRAME
        )
        == 0.0
    )
