"""治疗公式解析和纯计算入口。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from genshin_sim.core.attributes import (
    BONUS_HEALING_INCOMING,
    BONUS_HEALING_OUTGOING,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolution,
    AttributeResolveOptions,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    AttributeSystemError,
    TraceLevel,
)
from genshin_sim.core.systems.healing.errors import (
    HealingValidationError,
    InvalidHealingAttributeError,
    InvalidHealingResultError,
    UnsupportedHealingSubjectError,
)
from genshin_sim.core.systems.healing.models import (
    HealingComponentResult,
    HealingRequest,
    HealingResult,
    normalize_healing_zero,
    validate_healing_float,
)


@dataclass(frozen=True, slots=True)
class HealingResolver:
    """无状态治疗结算器，只返回理论治疗结果。"""

    attribute_resolver: AttributeResolver
    trace_level: TraceLevel = TraceLevel.FULL

    def resolve(self, request: HealingRequest) -> HealingResult:
        """按第一版治疗公式解析请求并返回不可变结果。"""

        _validate_request_subjects(request)
        if not isinstance(self.trace_level, TraceLevel):
            raise HealingValidationError("trace_level 不受支持")
        attribute_session = self.attribute_resolver.new_session()
        source_context = AttributeQueryContext(
            tags=request.tags,
            source_ref=request.source_context,
            target_ref=request.target_ref,
        )
        target_context = AttributeQueryContext(
            tags=request.tags,
            source_ref=request.source_context,
            target_ref=request.source_ref,
        )

        component_results: list[HealingComponentResult] = []
        for scaling in request.scaling_terms:
            resolution = _resolve_attribute(
                self.attribute_resolver,
                request.source_ref,
                scaling.attribute_key,
                request.frame,
                source_context,
                self.trace_level,
                attribute_session,
            )
            scaling_value = validate_healing_float(
                resolution.final_value,
                f"{scaling.component_key}.scaling_value",
            )
            value = _multiply_healing_values(
                scaling_value,
                scaling.coefficient,
                field_name=f"component {scaling.component_key} 的治疗贡献",
            )
            if not math.isfinite(value):
                raise InvalidHealingResultError(
                    f"component {scaling.component_key} 的治疗贡献必须是有限数字"
                )
            component_results.append(
                HealingComponentResult(
                    component_key=scaling.component_key,
                    attribute_key=scaling.attribute_key,
                    scaling_value=scaling_value,
                    coefficient=scaling.coefficient,
                    value=value,
                )
            )

        outgoing = _resolve_attribute(
            self.attribute_resolver,
            request.source_ref,
            BONUS_HEALING_OUTGOING,
            request.frame,
            source_context,
            self.trace_level,
            attribute_session,
        )
        incoming = _resolve_attribute(
            self.attribute_resolver,
            request.target_ref,
            BONUS_HEALING_INCOMING,
            request.frame,
            target_context,
            self.trace_level,
            attribute_session,
        )
        outgoing_bonus = validate_healing_float(
            outgoing.final_value,
            "outgoing_healing_bonus",
        )
        incoming_bonus = validate_healing_float(
            incoming.final_value,
            "incoming_healing_bonus",
        )

        base_healing = _sum_healing_values(
            (*(component.value for component in component_results), request.flat_healing),
            field_name="base_healing",
        )
        if not math.isfinite(base_healing) or base_healing < 0:
            raise InvalidHealingResultError("base_healing 必须是有限非负数")
        multiplier = _sum_healing_values(
            (1.0, outgoing_bonus, incoming_bonus),
            field_name="healing_bonus_multiplier",
        )
        if not math.isfinite(multiplier):
            raise InvalidHealingResultError("healing_bonus_multiplier 必须是有限数字")
        if multiplier < 0:
            raise InvalidHealingResultError("healing_bonus_multiplier 不能为负数")
        final_healing = _multiply_healing_values(
            base_healing,
            multiplier,
            field_name="final_healing",
        )
        if not math.isfinite(final_healing) or final_healing < 0:
            raise InvalidHealingResultError("final_healing 必须是有限非负数")

        return HealingResult(
            healing_id=request.healing_id,
            frame=request.frame,
            source_ref=request.source_ref,
            target_ref=request.target_ref,
            component_results=tuple(component_results),
            flat_healing=request.flat_healing,
            base_healing=base_healing,
            outgoing_healing_bonus=outgoing_bonus,
            incoming_healing_bonus=incoming_bonus,
            healing_bonus_multiplier=multiplier,
            final_healing=final_healing,
            source_context=request.source_context,
            tags=request.tags,
        )


def _sum_healing_values(values: tuple[float, ...], *, field_name: str) -> float:
    try:
        return normalize_healing_zero(math.fsum(values))
    except OverflowError as exc:
        raise InvalidHealingResultError(f"{field_name} 必须是有限数字") from exc


def _multiply_healing_values(left: float, right: float, *, field_name: str) -> float:
    try:
        return normalize_healing_zero(left * right)
    except OverflowError as exc:
        raise InvalidHealingResultError(f"{field_name} 必须是有限数字") from exc


def _validate_request_subjects(request: HealingRequest) -> None:
    """确保 resolver 只处理阶段 C 支持的角色对角色治疗。"""

    if not isinstance(request.source_ref, AttributeSubjectRef) or not isinstance(
        request.target_ref,
        AttributeSubjectRef,
    ):
        raise HealingValidationError("治疗来源和目标必须是 AttributeSubjectRef")
    if (
        request.source_ref.kind is not AttributeSubjectKind.CHARACTER
        or request.target_ref.kind is not AttributeSubjectKind.CHARACTER
    ):
        raise UnsupportedHealingSubjectError("治疗来源和目标第一版必须是角色主体")


def _resolve_attribute(
    resolver: AttributeResolver,
    subject_ref: AttributeSubjectRef,
    attribute_key,
    frame: int,
    context: AttributeQueryContext,
    trace_level: TraceLevel,
    session,
) -> AttributeResolution:
    """通过属性系统解析治疗公式输入，并转换属性错误类型。"""

    try:
        return resolver.resolve(
            AttributeQuery(
                subject_ref=subject_ref,
                attribute_key=attribute_key,
                frame=frame,
                context=context,
            ),
            options=AttributeResolveOptions(trace_level=trace_level),
            session=session,
        )
    except AttributeSystemError as exc:
        raise InvalidHealingAttributeError(f"无法解析治疗属性 {attribute_key}：{exc}") from exc
