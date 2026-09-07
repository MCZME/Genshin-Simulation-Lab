from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeQuery,
    ModifierProviderSpec,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.buff.definitions import BuffDefinition
from genshin_sim.core.systems.buff.errors import BuffModifierBindingError
from genshin_sim.core.systems.buff.protocols import BuffReader
from genshin_sim.core.systems.buff.resolver import scaled_modifier_value


@dataclass(frozen=True, slots=True)
class BuffAttributeModifierProvider:
    definition: BuffDefinition
    reader: BuffReader
    provider_spec: ModifierProviderSpec

    def __init__(self, definition: BuffDefinition, reader: BuffReader) -> None:
        provider_key = f"buff.attribute:{definition.definition_key}"
        object.__setattr__(self, "definition", definition)
        object.__setattr__(self, "reader", reader)
        object.__setattr__(
            self,
            "provider_spec",
            ModifierProviderSpec(
                provider_key=provider_key,
                writes=frozenset(
                    template.target_key for template in definition.attribute_modifiers
                ),
                private_namespace=definition.handler_key,
                owner_ref=None,
                display_name=definition.display_name,
            ),
        )

    def contribute(self, query: AttributeQuery, session: object) -> Sequence[ModifierTerm]:
        del session
        if query.attribute_key not in self.provider_spec.writes:
            return ()
        query_tags = query.context.tags
        terms: list[ModifierTerm] = []
        records = self.reader.active(
            query.frame,
            target_ref=query.subject_ref,
            definition_key=self.definition.definition_key,
        )
        for record in records:
            for resolved in record.state.resolved_modifiers:
                template = resolved.template
                if template.target_key != query.attribute_key:
                    continue
                if not template.matches_tags(query_tags):
                    continue
                value = scaled_modifier_value(record, resolved)
                if not math.isfinite(value):
                    raise BuffModifierBindingError(
                        f"Buff {record.instance_ref.to_key()} modifier {template.term_key} "
                        "结果必须是有限数字"
                    )
                terms.append(
                    ModifierTerm(
                        target_key=template.target_key,
                        stage=template.stage,
                        value=value,
                        provider_key=self.provider_spec.provider_key,
                        source_ref=RuntimeSourceRef(
                            RuntimeSourceKind.MECHANIC,
                            record.definition.mechanic_key,
                            record.instance_ref.to_key(),
                        ),
                        stacking_group=template.stacking_group,
                        audit_tags=(
                            *template.audit_tags,
                            "buff",
                            f"definition:{record.definition.definition_key}",
                            f"stacks:{record.state.stack_count}",
                        ),
                    )
                )
        return tuple(terms)
