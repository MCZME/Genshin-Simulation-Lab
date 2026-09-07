"""队伍规则装配：元素共鸣构成、激活与静态 provider。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.assembly.ports import (
    AuraFrozenReadAdapter,
    LunarCagePresenceReadAdapter,
    ShieldPresenceReadAdapter,
)
from genshin_sim.assets.models import CharacterAsset
from genshin_sim.content.team import create_resonance_definitions
from genshin_sim.core.attributes import StaticModifierProvider
from genshin_sim.core.elements import Element
from genshin_sim.core.simulation.team import TeamRuntimeState
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceAuraDurationTermProvider,
    ResonanceCooldownDurationTermProvider,
    ResonanceCryoCritDamageProvider,
    ResonanceDefinitionRegistry,
    ResonanceError,
    ResonanceGeoDamageProvider,
    ResonanceStore,
    TeamElementComposition,
    build_resonance_static_providers,
    evaluate_resonances,
)
from genshin_sim.core.systems.resonance.ports import (
    CharacterShieldPresenceReadPort,
    LunarCagePresenceReadPort,
)


class ResonanceAssetBundle(Protocol):
    """共鸣装配只需要槽位与角色资产的只读视图。"""

    @property
    def slot(self) -> int: ...

    @property
    def character(self) -> CharacterAsset: ...


@dataclass(frozen=True, slots=True)
class ResonanceRuntimeBundle:
    """元素共鸣装配产物：定义、构成、激活集、Store 与静态 provider。"""

    definitions: ResonanceDefinitionRegistry
    composition: TeamElementComposition
    activation: ResonanceActivation
    store: ResonanceStore
    static_providers: tuple[StaticModifierProvider, ...]
    aura_duration_term_provider: ResonanceAuraDurationTermProvider
    cooldown_duration_term_provider: ResonanceCooldownDurationTermProvider
    damage_providers: tuple[
        ResonanceCryoCritDamageProvider | ResonanceGeoDamageProvider,
        ...,
    ]

    def bind_runtime_ports(
        self,
        *,
        aura_runtime,
        reaction_runtime,
        shield_runtime,
        team_state: TeamRuntimeState,
    ) -> tuple[CharacterShieldPresenceReadPort, LunarCagePresenceReadPort]:
        """领域运行态创建后绑定只读端口；未绑定时 provider 返回空。"""

        aura_frozen_port = AuraFrozenReadAdapter(aura_runtime, reaction_runtime)
        shield_port = ShieldPresenceReadAdapter(shield_runtime, team_state)
        lunar_cage_port = LunarCagePresenceReadAdapter(reaction_runtime)
        for provider in self.damage_providers:
            if isinstance(provider, ResonanceCryoCritDamageProvider):
                provider.bind_runtime_ports(aura_frozen_port=aura_frozen_port)
            elif isinstance(provider, ResonanceGeoDamageProvider):
                provider.bind_runtime_ports(
                    shield_port=shield_port,
                    lunar_cage_port=lunar_cage_port,
                )
        return (shield_port, lunar_cage_port)


def build_resonance_bundle(
    assets: Sequence[ResonanceAssetBundle],
) -> ResonanceRuntimeBundle:
    """从槽位资产计算队伍元素构成并确定活跃共鸣集合。"""

    try:
        composition = _composition_from_assets(assets)
        definitions = ResonanceDefinitionRegistry(create_resonance_definitions())
        activation = evaluate_resonances(composition, definitions.definitions)
        store = ResonanceStore(activation=activation, composition=composition)
        providers = build_resonance_static_providers(
            activation=activation,
            definitions=definitions.definitions,
            slots=tuple(bundle.slot for bundle in assets),
        )
        aura_provider = ResonanceAuraDurationTermProvider(
            activation,
            definitions.definitions,
        )
        cooldown_provider = ResonanceCooldownDurationTermProvider(
            activation,
            definitions.definitions,
        )
        damage_providers = (
            ResonanceCryoCritDamageProvider("resonance.cryo" in activation.active_keys),
            ResonanceGeoDamageProvider("resonance.geo" in activation.active_keys),
        )
    except ResonanceError as exc:
        raise InvalidRuntimePayloadError(f"元素共鸣组装失败：{exc}") from exc
    return ResonanceRuntimeBundle(
        definitions=definitions,
        composition=composition,
        activation=activation,
        store=store,
        static_providers=providers,
        aura_duration_term_provider=aura_provider,
        cooldown_duration_term_provider=cooldown_provider,
        damage_providers=damage_providers,
    )


def _composition_from_assets(
    assets: Sequence[ResonanceAssetBundle],
) -> TeamElementComposition:
    counts: dict[Element, int] = {}
    for bundle in assets:
        try:
            element = Element(bundle.character.element)
        except ValueError as exc:
            raise InvalidRuntimePayloadError(
                f"槽位 {bundle.slot} 角色元素不受元素共鸣支持：{bundle.character.element!r}"
            ) from exc
        if element is Element.PHYSICAL:
            raise InvalidRuntimePayloadError(
                f"槽位 {bundle.slot} 角色元素不能参与元素共鸣：physical"
            )
        counts[element] = counts.get(element, 0) + 1
    return TeamElementComposition.from_counts(len(assets), counts)
