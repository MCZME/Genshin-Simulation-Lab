"""月兆装配：从角色内容 metadata 识别月兆角色并构造领域运行态。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.assets.models import CharacterAsset
from genshin_sim.content.definitions.content_unit import ContentUnit, ContentUnitOwnerType
from genshin_sim.content.team.moonsign import (
    MOONSIGN_BONUS_CAP,
    MOONSIGN_BONUS_DURATION_FRAMES,
    MOONSIGN_SCALING_BY_ELEMENT,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.moonsign import (
    MoonsignRuntime,
    MoonsignStore,
    resolve_moonsign_level,
)


class MoonsignAssetBundle(Protocol):
    @property
    def slot(self) -> int: ...

    @property
    def character(self) -> CharacterAsset: ...


@dataclass(frozen=True, slots=True)
class MoonsignRuntimeBundle:
    """月兆装配产物：Store 与 Runtime。"""

    store: MoonsignStore
    runtime: MoonsignRuntime


def build_moonsign_bundle(
    *,
    content_units: Sequence[ContentUnit],
    assets: Sequence[MoonsignAssetBundle],
    attribute_resolver,
    event_engine: EventEngine,
) -> MoonsignRuntimeBundle:
    """按 content metadata 的 ``moonsign: true`` 标记识别月兆角色。"""

    slots = sorted(
        {
            unit.slot
            for unit in content_units
            if unit.owner_type is ContentUnitOwnerType.CHARACTER
            and unit.slot is not None
            and unit.metadata.get("moonsign") is True
        }
    )
    refs = tuple(AttributeSubjectRef.character(f"character:slot_{slot}") for slot in slots)
    store = MoonsignStore()
    store.set_level(resolve_moonsign_level(len(refs)), refs)
    element_by_slot: dict[int, Element] = {}
    for bundle in assets:
        try:
            element = Element(bundle.character.element)
        except ValueError as exc:
            raise InvalidRuntimePayloadError(
                f"槽位 {bundle.slot} 角色元素不受月兆支持：{bundle.character.element!r}"
            ) from exc
        if element is Element.PHYSICAL:
            raise InvalidRuntimePayloadError(f"槽位 {bundle.slot} 角色元素不能参与月兆：physical")
        element_by_slot[bundle.slot] = element
    runtime = MoonsignRuntime(
        store,
        event_engine,
        attribute_resolver,
        MOONSIGN_SCALING_BY_ELEMENT,
        cap=MOONSIGN_BONUS_CAP,
        duration_frames=MOONSIGN_BONUS_DURATION_FRAMES,
        element_by_slot=element_by_slot,
    )
    return MoonsignRuntimeBundle(store=store, runtime=runtime)
