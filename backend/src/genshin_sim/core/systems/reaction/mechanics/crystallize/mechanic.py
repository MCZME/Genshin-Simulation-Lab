"""普通结晶的四个单 Aura 方向，不直接访问 Space 或创建 State。"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element
from genshin_sim.core.systems.reaction.establishment_gates import (
    ReactionEstablishmentGateDefinition,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize.formulas import (
    capture_crystallize_shield_basis,
)
from genshin_sim.core.systems.reaction.models import (
    CrystallizeReactionProfile,
    CrystallizeShardStateCreationIntent,
    ElementalTransitionEffect,
    ReactionDefinition,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionResolution,
    ReactionTriggerSignature,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import ReactionStateInstanceRef

CRYSTALLIZE_REACTION_KEY = "reaction.crystallize"
CRYSTALLIZE_HANDLER_KEY = "reaction_handler.crystallize"
GEO_ON_PYRO = "incoming_geo_on_pyro"
GEO_ON_HYDRO = "incoming_geo_on_hydro"
GEO_ON_ELECTRO = "incoming_geo_on_electro"
GEO_ON_CRYO = "incoming_geo_on_cryo"
CRYSTALLIZE_ESTABLISHMENT_GATE_KEY = "reaction_gate.crystallize.establishment"
CRYSTALLIZE_SHARD_STATE_KEY = "reaction_state.crystallize_shard"
CRYSTALLIZE_FORMULA_KEY = "reaction_formula.crystallize_shield_basis"
CRYSTALLIZE_LIFETIME_FRAMES = 900
CRYSTALLIZE_ESTABLISHMENT_GATE_WINDOW_FRAMES = 60


class CrystallizeRule:
    """单 Aura 结晶；水雷与冻结复合候选由 Runtime 的显式后续路径处理。"""

    def evaluate(
        self,
        request: ReactionEvaluationRequest,
        definition: ReactionDefinition,
    ) -> ReactionResolution | None:
        if (
            request.incoming_element is not Element.GEO
            or request.has_active_frozen_state
            or request.observed_aura.component_for(AuraKind.FROZEN) is not None
        ):
            return None
        candidates = tuple(
            (aura_kind, component.current_amount)
            for aura_kind in (AuraKind.PYRO, AuraKind.HYDRO, AuraKind.ELECTRO, AuraKind.CRYO)
            if (component := request.observed_aura.component_for(aura_kind)) is not None
            and not component.current_amount.is_zero
        )
        if len(candidates) != 1:
            return None
        aura_kind, aura_before = candidates[0]
        direction, shard_element = _direction_for(aura_kind)
        profile = definition.profile_for(direction)
        if not isinstance(profile, CrystallizeReactionProfile):
            raise ValueError("结晶方向必须使用 CrystallizeReactionProfile")
        if profile.shard_element is not shard_element:
            raise ValueError("结晶 Profile 的晶片元素与 Aura 方向不一致")
        observation = request.crystallize_source_observation
        if observation is None:
            raise ValueError("结晶需要已捕获的结晶来源观察")

        geo_consumed = request.incoming_amount.minimum(aura_before * 2)
        if geo_consumed.is_zero:
            return None
        aura_consumed = geo_consumed / 2
        occurrence_ref = f"{request.interaction_id}:occurrence:{request.order}"
        instance_ref = ReactionStateInstanceRef(
            f"reaction-state:crystallize-shard:{occurrence_ref}"
        )
        space_entity_ref = f"reaction_object:crystallize_shard:{occurrence_ref}"
        expires_at_frame = request.frame + profile.lifetime_frames
        basis = capture_crystallize_shield_basis(
            observation,
            captured_frame=request.frame,
        )
        shard_creation = CrystallizeShardStateCreationIntent(
            intent_ref=f"{occurrence_ref}:crystallize-shard-state-create",
            parent_occurrence_ref=occurrence_ref,
            instance_ref=instance_ref,
            subject_ref=request.subject_ref,
            space_entity_ref=space_entity_ref,
            element=profile.shard_element,
            trigger_source=request.source_ref,
            captured_shield_basis=basis,
            created_frame=request.frame,
            expires_at_frame=expires_at_frame,
        )
        spatial_creation = SpatialEntityCreationEffect(
            effect_ref=f"{occurrence_ref}:spatial-entity-create",
            parent_occurrence_ref=occurrence_ref,
            space_entity_ref=space_entity_ref,
            owner_key=definition.reaction_key,
            source_key=instance_ref.value,
            tags=("reaction_object", "crystallize_shard"),
            created_frame=request.frame,
            expires_at_frame=expires_at_frame,
        )
        occurrence = ReactionOccurrence(
            occurrence_ref=occurrence_ref,
            interaction_id=request.interaction_id,
            reaction_key=definition.reaction_key,
            direction_key=direction,
            profile_key=profile.profile_key,
            source_ref=request.source_ref,
            subject_ref=request.subject_ref,
            transition=ElementalTransitionEffect(
                aura_kind=aura_kind,
                incoming_before=request.incoming_amount,
                incoming_consumed=geo_consumed,
                incoming_remaining=request.incoming_amount - geo_consumed,
                aura_before=aura_before,
                aura_consumed=aura_consumed,
                aura_remaining=aura_before - aura_consumed,
            ),
            crystallize_shard_state_creation=shard_creation,
            spatial_entity_creation=spatial_creation,
        )
        return ReactionResolution(request, occurrence, None)


def crystallize_definition() -> ReactionDefinition:
    return ReactionDefinition(
        CRYSTALLIZE_REACTION_KEY,
        CRYSTALLIZE_HANDLER_KEY,
        (
            ReactionTriggerSignature(Element.GEO, AuraKind.PYRO, GEO_ON_PYRO),
            ReactionTriggerSignature(Element.GEO, AuraKind.HYDRO, GEO_ON_HYDRO),
            ReactionTriggerSignature(Element.GEO, AuraKind.ELECTRO, GEO_ON_ELECTRO),
            ReactionTriggerSignature(Element.GEO, AuraKind.CRYO, GEO_ON_CRYO),
        ),
        (
            CrystallizeReactionProfile(
                "reaction_profile.crystallize.incoming_geo_on_pyro",
                CRYSTALLIZE_REACTION_KEY,
                GEO_ON_PYRO,
                Element.GEO,
                Element.PYRO,
                CRYSTALLIZE_ESTABLISHMENT_GATE_KEY,
                CRYSTALLIZE_SHARD_STATE_KEY,
                CRYSTALLIZE_FORMULA_KEY,
                CRYSTALLIZE_LIFETIME_FRAMES,
            ),
            CrystallizeReactionProfile(
                "reaction_profile.crystallize.incoming_geo_on_hydro",
                CRYSTALLIZE_REACTION_KEY,
                GEO_ON_HYDRO,
                Element.GEO,
                Element.HYDRO,
                CRYSTALLIZE_ESTABLISHMENT_GATE_KEY,
                CRYSTALLIZE_SHARD_STATE_KEY,
                CRYSTALLIZE_FORMULA_KEY,
                CRYSTALLIZE_LIFETIME_FRAMES,
            ),
            CrystallizeReactionProfile(
                "reaction_profile.crystallize.incoming_geo_on_electro",
                CRYSTALLIZE_REACTION_KEY,
                GEO_ON_ELECTRO,
                Element.GEO,
                Element.ELECTRO,
                CRYSTALLIZE_ESTABLISHMENT_GATE_KEY,
                CRYSTALLIZE_SHARD_STATE_KEY,
                CRYSTALLIZE_FORMULA_KEY,
                CRYSTALLIZE_LIFETIME_FRAMES,
            ),
            CrystallizeReactionProfile(
                "reaction_profile.crystallize.incoming_geo_on_cryo",
                CRYSTALLIZE_REACTION_KEY,
                GEO_ON_CRYO,
                Element.GEO,
                Element.CRYO,
                CRYSTALLIZE_ESTABLISHMENT_GATE_KEY,
                CRYSTALLIZE_SHARD_STATE_KEY,
                CRYSTALLIZE_FORMULA_KEY,
                CRYSTALLIZE_LIFETIME_FRAMES,
            ),
        ),
        CrystallizeRule(),
    )


def crystallize_establishment_gate_definition() -> ReactionEstablishmentGateDefinition:
    return ReactionEstablishmentGateDefinition(
        CRYSTALLIZE_ESTABLISHMENT_GATE_KEY,
        window_frames=CRYSTALLIZE_ESTABLISHMENT_GATE_WINDOW_FRAMES,
        max_occurrences=1,
    )


def _direction_for(aura_kind: AuraKind) -> tuple[str, Element]:
    match aura_kind:
        case AuraKind.PYRO:
            return GEO_ON_PYRO, Element.PYRO
        case AuraKind.HYDRO:
            return GEO_ON_HYDRO, Element.HYDRO
        case AuraKind.ELECTRO:
            return GEO_ON_ELECTRO, Element.ELECTRO
        case AuraKind.CRYO:
            return GEO_ON_CRYO, Element.CRYO
        case _:
            raise ValueError("普通结晶只支持火、水、雷或冰 Aura")
