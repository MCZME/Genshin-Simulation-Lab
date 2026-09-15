from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from genshin_sim.core.attributes import (
    AttributeQuery,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.attributes.ports import TeamScopeProjectionPort
from genshin_sim.core.systems.buff.definitions import BuffDefinition
from genshin_sim.core.systems.buff.errors import BuffModifierBindingError
from genshin_sim.core.systems.buff.protocols import BuffReader
from genshin_sim.core.systems.buff.resolver import scaled_modifier_value


@dataclass(frozen=True, slots=True)
class BuffAttributeModifierProvider:
    definition: BuffDefinition
    reader: BuffReader
    provider_spec: ModifierProviderSpec
    # 队伍作用域投影端口；装配期由 bind_runtime_ports 注入，未绑定时为 None。
    _team_scope_port: TeamScopeProjectionPort | None = field(default=None, init=False)

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
        object.__setattr__(self, "_team_scope_port", None)

    def bind_runtime_ports(
        self,
        *,
        team_scope_projection_port: TeamScopeProjectionPort,
    ) -> None:
        """绑定队伍作用域投影端口；未绑定时只做精确主体匹配。"""

        object.__setattr__(self, "_team_scope_port", team_scope_projection_port)

    def contribute(self, query: AttributeQuery, session: object) -> Sequence[ModifierTerm]:
        del session
        if query.attribute_key not in self.provider_spec.writes:
            return ()
        query_tags = query.context.tags
        terms: list[ModifierTerm] = []
        for record in self._matching_records(query):
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

    def _matching_records(self, query: AttributeQuery):
        """按主体精确匹配，并叠加队伍作用域投影。

        队伍作用域记录挂在队伍稳定作用域 id 上，因此查询角色主体时需要额外
        收集：`TEAM` 记录作用于队伍全部角色；`ACTIVE_CHARACTER` 记录只作用于
        当前场上角色。未绑定投影端口时不做任何额外收集。
        """

        subject_ref = query.subject_ref
        records = list(
            self.reader.active(
                query.frame,
                target_ref=subject_ref,
                definition_key=self.definition.definition_key,
            )
        )
        port = self._team_scope_port
        if port is None or subject_ref.kind is not AttributeSubjectKind.CHARACTER:
            return tuple(records)
        team_ref = port.team_scope_for(subject_ref)
        if team_ref is None:
            return tuple(records)
        records.extend(
            self.reader.active(
                query.frame,
                target_ref=AttributeSubjectRef.team(team_ref),
                definition_key=self.definition.definition_key,
            )
        )
        if port.is_active_character(subject_ref):
            records.extend(
                self.reader.active(
                    query.frame,
                    target_ref=AttributeSubjectRef.active_character(team_ref),
                    definition_key=self.definition.definition_key,
                )
            )
        # 记录来自单一定义，instance_ref 唯一，但显式去重以防御同一主体重复读取。
        return tuple({record.instance_ref: record for record in records}.values())
