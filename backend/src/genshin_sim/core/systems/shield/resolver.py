"""护盾创建公式的纯属性解析与计算入口。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes import (
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolution,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSystemError,
    TraceLevel,
)
from genshin_sim.core.systems.shield.errors import (
    ShieldAttributeError,
    ShieldCapacityError,
    ShieldValidationError,
)
from genshin_sim.core.systems.shield.formulas import (
    ShieldCapacityComponentResult,
    ShieldCapacityFormula,
    ShieldCapacityFormulaResult,
    ShieldNativeMultiplierResult,
    normalize_shield_zero,
    validate_shield_float,
)
from genshin_sim.core.systems.shield.models import ShieldGrantRequest, ShieldGrantResolution


@dataclass(frozen=True, slots=True)
class ShieldResolver:
    """只解析创建帧属性并返回原生授予量，不读写运行态。"""

    attribute_resolver: AttributeResolver
    trace_level: TraceLevel = TraceLevel.FULL

    def resolve(self, request: ShieldGrantRequest) -> ShieldGrantResolution:
        if not isinstance(request, ShieldGrantRequest):
            raise ShieldValidationError("request 必须是 ShieldGrantRequest")
        if not isinstance(self.trace_level, TraceLevel):
            raise ShieldValidationError("trace_level 不受支持")

        session = self.attribute_resolver.new_session()
        query_context = AttributeQueryContext(
            tags=request.tags,
            source_ref=request.source_context,
        )
        attribute_trace: list[AttributeResolution] = []
        grant = self._resolve_formula(
            request.grant_formula,
            request=request,
            query_context=query_context,
            session=session,
            attribute_trace=attribute_trace,
        )
        capacity_limit = None
        if request.capacity_limit_formula is not None:
            limit = self._resolve_formula(
                request.capacity_limit_formula,
                request=request,
                query_context=query_context,
                session=session,
                attribute_trace=attribute_trace,
            )
            capacity_limit = limit.native_absorption

        return ShieldGrantResolution(
            grant_id=request.grant_id,
            frame=request.frame,
            creator_ref=request.creator_ref,
            protection_ref=request.protection_ref,
            component_results=grant.component_results,
            flat_absorption=grant.flat_absorption,
            native_multiplier_results=grant.native_multiplier_results,
            granted_absorption=grant.native_absorption,
            capacity_limit=capacity_limit,
            attribute_trace=tuple(attribute_trace),
            source_context=request.source_context,
        )

    def _resolve_formula(
        self,
        formula: ShieldCapacityFormula,
        *,
        request: ShieldGrantRequest,
        query_context: AttributeQueryContext,
        session,
        attribute_trace: list[AttributeResolution],
    ) -> ShieldCapacityFormulaResult:
        component_results: list[ShieldCapacityComponentResult] = []
        for term in formula.scaling_terms:
            query = AttributeQuery(
                subject_ref=request.creator_ref,
                attribute_key=term.attribute_key,
                frame=request.frame,
                context=query_context,
            )
            try:
                resolution = self.attribute_resolver.resolve(
                    query,
                    options=AttributeResolveOptions(trace_level=self.trace_level),
                    session=session,
                )
            except AttributeSystemError as exc:
                raise ShieldAttributeError(
                    f"无法解析护盾创建属性 {term.attribute_key}：{exc}"
                ) from exc
            attribute_value = validate_shield_float(
                resolution.final_value,
                f"{term.component_key}.attribute_value",
            )
            try:
                value = normalize_shield_zero(attribute_value * term.coefficient)
            except OverflowError as exc:
                raise ShieldCapacityError(
                    f"护盾 component {term.component_key} 结果必须是有限数字"
                ) from exc
            if not math.isfinite(value):
                raise ShieldCapacityError(f"护盾 component {term.component_key} 结果必须是有限数字")
            component_results.append(
                ShieldCapacityComponentResult(
                    component_key=term.component_key,
                    attribute_key=term.attribute_key,
                    attribute_value=attribute_value,
                    coefficient=term.coefficient,
                    value=value,
                )
            )
            attribute_trace.append(resolution)

        try:
            base_absorption = normalize_shield_zero(
                math.fsum(
                    (
                        *(component.value for component in component_results),
                        formula.flat_absorption,
                    )
                )
            )
        except OverflowError as exc:
            raise ShieldCapacityError("base_absorption 必须是有限数字") from exc
        if not math.isfinite(base_absorption) or base_absorption <= 0:
            raise ShieldCapacityError("base_absorption 必须是有限正数")

        multiplier_results = tuple(
            ShieldNativeMultiplierResult(
                multiplier_key=term.multiplier_key,
                multiplier=term.multiplier,
                source_context=term.source_context,
            )
            for term in formula.native_multipliers
        )
        native_multiplier = 1.0
        for multiplier in multiplier_results:
            try:
                native_multiplier *= multiplier.multiplier
            except OverflowError as exc:
                raise ShieldCapacityError("native_multiplier 必须是有限数字") from exc
            if not math.isfinite(native_multiplier):
                raise ShieldCapacityError("native_multiplier 必须是有限数字")
        try:
            native_absorption = normalize_shield_zero(base_absorption * native_multiplier)
        except OverflowError as exc:
            raise ShieldCapacityError("native_absorption 必须是有限数字") from exc
        if not math.isfinite(native_absorption) or native_absorption <= 0:
            raise ShieldCapacityError("native_absorption 必须是有限正数")

        return ShieldCapacityFormulaResult(
            component_results=tuple(component_results),
            flat_absorption=formula.flat_absorption,
            base_absorption=base_absorption,
            native_multiplier_results=multiplier_results,
            native_multiplier=native_multiplier,
            native_absorption=native_absorption,
        )
