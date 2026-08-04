"""Aura 的计划、精确衰减和原子内存提交。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSubjectRef,
    aura_kind_for_element,
)
from genshin_sim.core.events import AuraDepletedPayload, EventType, GameEvent
from genshin_sim.core.systems.aura.enums import AuraApplicationOutcome, AuraDecayMode, AuraStrength
from genshin_sim.core.systems.aura.models import (
    AuraApplicationRequest,
    AuraApplicationResult,
    AuraCommitReceipt,
    AuraComponent,
    AuraContribution,
    AuraContributionRef,
    AuraInstanceRef,
    AuraMutationPlan,
    AuraSnapshot,
    AuraStateLinkMutationRequest,
    AuraTargetRecord,
    AuraTransitionResult,
    AuraView,
    BurningAuraApplicationRequest,
    BurningAuraEstablishmentRequest,
    FrozenAuraApplicationRequest,
    QuickenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura.profiles import attached_amount, quicken_decay_profile


class AuraStoreConflictError(RuntimeError):
    pass


class UnsupportedAuraCombinationError(ValueError):
    """第一版未支持的异种持久 Aura 组合被请求时抛出的错误。"""


class AuraEventPublicationError(RuntimeError):
    """Aura 领域事实发布期间发生写入请求时抛出的错误。"""


class AuraBatchPlanner:
    """批次内 Aura 投影，不会写入真实 Store。"""

    def __init__(self, runtime: AuraRuntime, frame: int, batch_id: str) -> None:
        self._runtime = runtime
        self.frame = frame
        self.batch_id = batch_id
        self._records = dict(runtime._records)
        self._expected_store_version = runtime.version
        self._applications: list[AuraApplicationResult] = []
        self._transitions: list[AuraTransitionResult] = []
        self._request_ids: set[str] = set()
        self._interaction_ids: set[str] = set()
        self._orders: set[int] = set()
        self._instance_sequence = runtime._instance_sequence
        self._contribution_sequence = runtime._contribution_sequence
        self._sealed = False

    def view(self, subject_ref: ElementalSubjectRef) -> AuraView:
        record = self._records.get(subject_ref)
        return AuraView(
            subject_ref,
            () if record is None else record.components,
            0 if record is None else record.revision,
        )

    def apply(self, request: AuraApplicationRequest) -> AuraApplicationResult:
        self._assert_open()
        if request.frame != self.frame:
            raise ValueError("Aura 请求帧与所属批次不一致")
        if request.request_id in self._request_ids:
            raise ValueError(f"重复的 Aura request_id：{request.request_id}")
        if request.order in self._orders:
            raise ValueError(f"重复的 Aura order：{request.order}")
        if request.application_coefficient.is_zero:
            raise ValueError("元素施加系数为零时不能创建 Aura 请求")
        aura_kind = aura_kind_for_element(request.element)
        if aura_kind is None:
            raise ValueError(f"{request.element.value} 不能形成第一版持久 Aura")
        amount = attached_amount(
            request.base_strength,
            request.application_coefficient,
            request.loss_policy,
            request.effective_raw_amount,
        )
        record = self._records.get(request.target_ref)
        component = None if record is None else record.component_for(aura_kind)
        if (
            component is None
            and record is not None
            and not _can_add_ordinary_aura(
                record,
                aura_kind,
            )
        ):
            existing = ", ".join(item.aura_kind.value for item in record.components)
            raise UnsupportedAuraCombinationError(
                f"第一版不支持 {existing} 与 {aura_kind.value} 的持久 Aura 共存"
            )
        result, updated = self._apply_component(request, aura_kind, amount, component)
        previous_components = () if record is None else record.components
        components = tuple(
            item for item in previous_components if item.aura_kind is not aura_kind
        ) + (updated,)
        self._records[request.target_ref] = AuraTargetRecord(
            request.target_ref,
            components,
            1 if record is None else record.revision + (updated != component),
        )
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        self._applications.append(result)
        return result

    def apply_quicken(self, request: QuickenAuraApplicationRequest) -> AuraApplicationResult:
        """由 Reaction 的强类型计划创建或取大覆盖派生激元素。

        激元素不复用普通同元素 Aura 的贡献叠加和衰减率升级规则：
        它在一个连续实例中恰好保留一条派生贡献，只有新量严格更大时才
        替换该贡献的来源、数量与精确衰减档案。覆盖始终保留实例、贡献与
        Quicken Link 身份。
        """""

        self._assert_open()
        self._assert_request_identity(request.request_id, request.order, request.frame, "激元素")
        record = self._records.get(request.target_ref)
        before = None if record is None else record.component_for(AuraKind.QUICKEN)
        if before is not None:
            if request.state_link_ref not in before.state_link_refs:
                raise ValueError("同一主体不能用不同 Link 覆盖激元素")
            if len(before.contributions) != 1 or before.decay_profile is None:
                raise ValueError("活动激元素缺少唯一派生贡献或精确衰减档案")

        selected_new = before is None or request.amount > before.current_amount
        if before is None:
            contribution = AuraContribution(
                request.contribution_ref,
                request.source_ref,
                request.amount,
                request.source_ref,
                request.frame,
                request.frame,
                request.frame,
            )
            quicken = AuraComponent(
                AuraInstanceRef(self._next_instance_ref()),
                AuraKind.QUICKEN,
                (contribution,),
                AuraStrength.WEAK,
                request.source_ref,
                request.frame,
                request.frame,
                request.frame,
                state_link_refs=(request.state_link_ref,),
                decay_profile=quicken_decay_profile(request.amount),
            )
        elif selected_new:
            previous = before.contributions[0]
            contribution = AuraContribution(
                previous.contribution_ref,
                request.source_ref,
                request.amount,
                request.source_ref,
                previous.created_frame,
                request.frame,
                request.frame,
            )
            quicken = replace(
                before,
                contributions=(contribution,),
                decay_origin=request.source_ref,
                last_applied_frame=request.frame,
                last_changed_frame=request.frame,
                decay_profile=quicken_decay_profile(request.amount),
            )
        else:
            quicken = replace(before, last_applied_frame=request.frame)

        components = () if record is None else record.components
        components = tuple(
            item for item in components if item.aura_kind is not AuraKind.QUICKEN
        ) + (quicken,)
        self._records[request.target_ref] = AuraTargetRecord(
            request.target_ref,
            components,
            1 if record is None else record.revision + (quicken != before),
        )
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        result = AuraApplicationResult(
            request.request_id,
            request.application_id,
            request.target_ref,
            AuraKind.QUICKEN,
            AuraApplicationOutcome.CREATED
            if before is None
            else AuraApplicationOutcome.DERIVED_REPLACED
            if selected_new
            else AuraApplicationOutcome.UNCHANGED,
            before,
            quicken,
        )
        self._applications.append(result)
        return result

    def apply_frozen(self, request: FrozenAuraApplicationRequest) -> AuraApplicationResult:
        self._assert_open()
        if request.frame != self.frame:
            raise ValueError("冻元素请求帧与所属批次不一致")
        if request.request_id in self._request_ids:
            raise ValueError(f"重复的 Aura request_id：{request.request_id}")
        if request.order in self._orders:
            raise ValueError(f"重复的 Aura order：{request.order}")
        record = self._records.get(request.target_ref)
        before = None if record is None else record.component_for(AuraKind.FROZEN)
        if before is not None and before.state_link_refs != (request.state_link_ref,):
            raise ValueError("同一主体不能用不同 Link 刷新冻元素")
        stacked_amount = (
            request.amount
            if before is None or request.replace_existing_amount
            else before.current_amount.maximum(request.amount)
        )
        contribution = AuraContribution(
            (
                AuraContributionRef(self._next_contribution_ref())
                if before is None
                else before.contributions[0].contribution_ref
            ),
            request.source_ref,
            stacked_amount,
            request.source_ref,
            request.frame if before is None else before.contributions[0].created_frame,
            request.frame,
            request.frame,
        )
        frozen = AuraComponent(
            AuraInstanceRef(self._next_instance_ref()) if before is None else before.instance_ref,
            AuraKind.FROZEN,
            (contribution,),
            AuraStrength.WEAK,
            request.source_ref,
            request.frame if before is None else before.created_frame,
            request.frame,
            request.frame,
            state_link_refs=(request.state_link_ref,),
            decay_mode=AuraDecayMode.STATE_LINKED,
        )
        components = () if record is None else record.components
        components = tuple(item for item in components if item.aura_kind is not AuraKind.FROZEN) + (
            frozen,
        )
        self._records[request.target_ref] = AuraTargetRecord(
            request.target_ref,
            components,
            1 if record is None else record.revision + (frozen != before),
        )
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        result = AuraApplicationResult(
            request.request_id,
            request.application_id,
            request.target_ref,
            AuraKind.FROZEN,
            AuraApplicationOutcome.CREATED
            if before is None
            else AuraApplicationOutcome.DERIVED_REPLACED,
            before,
            frozen,
        )
        self._applications.append(result)
        return result

    def apply_burning(self, request: BurningAuraApplicationRequest) -> AuraApplicationResult:
        """由 Reaction 的强类型计划创建或刷新派生燃元素。"""

        self._assert_open()
        self._assert_request_identity(request.request_id, request.order, request.frame, "燃元素")
        record = self._records.get(request.target_ref)
        dendro_like = () if record is None else tuple(
            component
            for component in record.components
            if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
            and request.state_link_ref in component.state_link_refs
            and component.decay_mode is AuraDecayMode.REACTION_MANAGED
        )
        if (
            record is None
            or not dendro_like
        ):
            raise ValueError("燃元素必须与受 Reaction 管理且携带同一 Link 的类草 Aura 同时存在")
        before = record.component_for(AuraKind.BURNING)
        if before is not None and before.state_link_refs != (request.state_link_ref,):
            raise ValueError("同一主体不能用不同 Link 刷新燃元素")
        stacked_amount = (
            request.amount
            if before is None or request.replace_existing_amount
            else before.current_amount.maximum(request.amount)
        )
        contribution = AuraContribution(
            (
                AuraContributionRef(self._next_contribution_ref())
                if before is None
                else before.contributions[0].contribution_ref
            ),
            request.source_ref,
            stacked_amount,
            request.source_ref,
            request.frame if before is None else before.contributions[0].created_frame,
            request.frame,
            request.frame,
        )
        burning = AuraComponent(
            AuraInstanceRef(self._next_instance_ref()) if before is None else before.instance_ref,
            AuraKind.BURNING,
            (contribution,),
            AuraStrength.WEAK,
            request.source_ref,
            request.frame if before is None else before.created_frame,
            request.frame,
            request.frame,
            state_link_refs=(request.state_link_ref,),
            decay_mode=AuraDecayMode.STATE_LINKED,
        )
        components = tuple(
            item for item in record.components if item.aura_kind is not AuraKind.BURNING
        ) + (burning,)
        self._records[request.target_ref] = AuraTargetRecord(
            request.target_ref,
            components,
            record.revision + (burning != before),
        )
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        result = AuraApplicationResult(
            request.request_id,
            request.application_id,
            request.target_ref,
            AuraKind.BURNING,
            AuraApplicationOutcome.CREATED
            if before is None
            else AuraApplicationOutcome.DERIVED_REPLACED,
            before,
            burning,
        )
        self._applications.append(result)
        return result

    def establish_burning(
        self,
        request: BurningAuraEstablishmentRequest,
    ) -> tuple[AuraApplicationResult, AuraApplicationResult]:
        """原子建立普通后手 Aura、关联类草 Aura 和固定燃元素。

        首次建立时主体通常只有相反普通 Aura；
        燃元素耗尽后也允许从 DENDRO + PYRO 残留终态重建。
        两种起点都不能复用两次普通 ``apply`` 形成中间投影。
        该入口只接收完整双 Aura 请求，并一次性写入最终合法组合。
        """

        self._assert_open()
        incoming_request = request.incoming_application
        burning_request = request.burning_application
        self._assert_request_identity(
            incoming_request.request_id,
            incoming_request.order,
            incoming_request.frame,
            "燃烧后手 Aura",
        )
        self._assert_request_identity(
            burning_request.request_id,
            burning_request.order,
            burning_request.frame,
            "燃元素",
        )
        if incoming_request.application_coefficient.is_zero:
            raise ValueError("燃烧后手元素施加系数不能为零")
        record = self._records.get(incoming_request.target_ref)
        existing_kind = (
            AuraKind.DENDRO if incoming_request.element is Element.PYRO else AuraKind.PYRO
        )
        existing = None if record is None else record.component_for(existing_kind)
        existing_dendro_like = () if record is None else tuple(
            component
            for component in record.components
            if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
        )
        if incoming_request.element is Element.PYRO:
            has_opponent = bool(existing_dendro_like)
        else:
            has_opponent = existing is not None
        if (
            record is None
            or not has_opponent
            or record.component_for(AuraKind.BURNING) is not None
            or frozenset(component.aura_kind for component in record.components)
            not in {
                frozenset({AuraKind.DENDRO}),
                frozenset({AuraKind.QUICKEN}),
                frozenset({AuraKind.DENDRO, AuraKind.QUICKEN}),
                frozenset({AuraKind.PYRO}),
                frozenset({AuraKind.DENDRO, AuraKind.PYRO}),
            }
        ):
            raise ValueError("燃烧成立需要类草与后手火，或燃尽后的普通火草残留，且尚无燃元素")

        incoming_kind = aura_kind_for_element(incoming_request.element)
        assert incoming_kind is not None
        incoming_amount = attached_amount(
            incoming_request.base_strength,
            incoming_request.application_coefficient,
            incoming_request.loss_policy,
            incoming_request.effective_raw_amount,
        )
        existing_incoming = record.component_for(incoming_kind)
        incoming_result, incoming_component = self._apply_component(
            incoming_request,
            incoming_kind,
            incoming_amount,
            existing_incoming,
        )
        components_by_kind = {
            component.aura_kind: component
            for component in record.components
            if component.aura_kind not in {incoming_kind, AuraKind.BURNING}
        }
        components_by_kind[incoming_kind] = incoming_component
        for aura_kind in (AuraKind.DENDRO, AuraKind.QUICKEN):
            component = components_by_kind.get(aura_kind)
            if component is None:
                continue
            linked_component = replace(
                component,
                state_link_refs=tuple(
                    sorted(
                        (*component.state_link_refs, burning_request.state_link_ref),
                        key=lambda item: item.link_key,
                    )
                ),
                decay_mode=AuraDecayMode.REACTION_MANAGED,
            )
            components_by_kind[aura_kind] = linked_component
            if aura_kind is incoming_kind:
                incoming_component = linked_component
                incoming_result = replace(incoming_result, after=linked_component)

        contribution = AuraContribution(
            AuraContributionRef(self._next_contribution_ref()),
            burning_request.source_ref,
            burning_request.amount,
            burning_request.source_ref,
            burning_request.frame,
            burning_request.frame,
            burning_request.frame,
        )
        burning = AuraComponent(
            AuraInstanceRef(self._next_instance_ref()),
            AuraKind.BURNING,
            (contribution,),
            AuraStrength.WEAK,
            burning_request.source_ref,
            burning_request.frame,
            burning_request.frame,
            burning_request.frame,
            state_link_refs=(burning_request.state_link_ref,),
            decay_mode=AuraDecayMode.STATE_LINKED,
        )
        components_by_kind[AuraKind.BURNING] = burning
        self._records[incoming_request.target_ref] = AuraTargetRecord(
            incoming_request.target_ref,
            tuple(components_by_kind.values()),
            record.revision + 1,
        )
        self._request_ids.update((incoming_request.request_id, burning_request.request_id))
        self._orders.update((incoming_request.order, burning_request.order))
        burning_result = AuraApplicationResult(
            burning_request.request_id,
            burning_request.application_id,
            burning_request.target_ref,
            AuraKind.BURNING,
            AuraApplicationOutcome.CREATED,
            None,
            burning,
        )
        self._applications.extend((incoming_result, burning_result))
        return incoming_result, burning_result

    def mutate_state_links(self, request: AuraStateLinkMutationRequest) -> AuraComponent:
        """在本批次投影中增删 Link，并可显式切换衰减模式。"""

        self._assert_open()
        self._assert_request_identity(request.request_id, request.order, request.frame, "Aura Link")
        record = self._records.get(request.target_ref)
        component = None if record is None else record.component_for(request.aura_kind)
        if record is None or component is None:
            raise ValueError(f"元素交互主体不存在 {request.aura_kind.value} Aura")
        existing = set(component.state_link_refs)
        additions = set(request.add_link_refs)
        removals = set(request.remove_link_refs)
        if additions & existing:
            raise ValueError("不能重复添加已经存在的 Aura Link")
        if not removals <= existing:
            raise ValueError("不能删除不存在的 Aura Link")
        updated = replace(
            component,
            state_link_refs=tuple((existing | additions) - removals),
            decay_mode=request.decay_mode or component.decay_mode,
        )
        components = tuple(
            item for item in record.components if item.aura_kind is not request.aura_kind
        ) + (updated,)
        self._records[request.target_ref] = AuraTargetRecord(
            request.target_ref,
            components,
            record.revision + (updated != component),
        )
        self._request_ids.add(request.request_id)
        self._orders.add(request.order)
        return updated

    def consume(
        self,
        *,
        interaction_id: str,
        subject_ref: ElementalSubjectRef,
        aura_kind: AuraKind,
        amount: AuraAmount,
    ) -> AuraTransitionResult:
        self._assert_open()
        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise ValueError("interaction_id 必须是非空字符串")
        if interaction_id in self._interaction_ids:
            raise ValueError(f"重复的 Aura interaction_id：{interaction_id}")
        if not isinstance(amount, AuraAmount) or amount.is_zero:
            raise ValueError("Aura 消耗量必须是正的 AuraAmount")
        record = self._records.get(subject_ref)
        component = None if record is None else record.component_for(aura_kind)
        if record is None or component is None:
            raise ValueError(f"元素交互主体不存在 {aura_kind.value} Aura")
        actual = amount.minimum(component.current_amount)
        remaining_contributions = tuple(
            replace(
                contribution,
                remaining_amount=(
                    contribution.remaining_amount - actual.minimum(contribution.remaining_amount)
                ),
                last_changed_frame=self.frame,
            )
            for contribution in component.contributions
            if contribution.remaining_amount > actual.minimum(contribution.remaining_amount)
        )
        after_amount = component.current_amount - actual
        if remaining_contributions:
            updated = replace(
                component,
                contributions=remaining_contributions,
                last_changed_frame=self.frame,
            )
            components = tuple(
                item for item in record.components if item.aura_kind is not aura_kind
            ) + (updated,)
        else:
            components = tuple(
                item for item in record.components if item.aura_kind is not aura_kind
            )
        if components:
            self._records[subject_ref] = AuraTargetRecord(
                subject_ref,
                components,
                record.revision + 1,
            )
        else:
            self._records.pop(subject_ref, None)
        result = AuraTransitionResult(
            interaction_id, subject_ref, aura_kind, component.current_amount, actual, after_amount
        )
        self._interaction_ids.add(interaction_id)
        self._transitions.append(result)
        return result

    def seal(self) -> AuraMutationPlan:
        self._assert_open()
        self._sealed = True
        current_subjects = set(self._runtime._records)
        planned_subjects = set(self._records)
        replacements = tuple(
            sorted(
                self._records.values(),
                key=lambda item: (item.subject_ref.kind.value, item.subject_ref.entity_id),
            )
        )
        removed = tuple(
            sorted(
                current_subjects - planned_subjects,
                key=lambda item: (item.kind.value, item.entity_id),
            )
        )
        return AuraMutationPlan(
            operation_id=f"aura:{self.batch_id}",
            frame=self.frame,
            request_ids=tuple(sorted(self._request_ids)),
            expected_store_version=self._expected_store_version,
            replacements=replacements,
            removed_subject_refs=removed,
            application_results=tuple(self._applications),
            transition_results=tuple(self._transitions),
            interaction_ids=tuple(sorted(self._interaction_ids)),
            next_instance_sequence=self._instance_sequence,
            next_contribution_sequence=self._contribution_sequence,
        )

    def _apply_component(self, request, aura_kind, amount, component):
        if component is None:
            contribution = AuraContribution(
                AuraContributionRef(self._next_contribution_ref()),
                request.source_ref,
                amount,
                request.source_ref,
                request.frame,
                request.frame,
                request.frame,
            )
            after = AuraComponent(
                AuraInstanceRef(self._next_instance_ref()),
                aura_kind,
                (contribution,),
                request.base_strength,
                request.source_ref,
                request.frame,
                request.frame,
                request.frame,
                decay_profile=request.decay_profile,
            )
            return (
                AuraApplicationResult(
                    request.request_id,
                    request.application_id,
                    request.target_ref,
                    aura_kind,
                    AuraApplicationOutcome.CREATED,
                    None,
                    after,
                ),
                after,
            )
        previous = component.contribution_for(request.source_ref)
        amount_changed = previous is None or amount > previous.remaining_amount
        profile_changed = (
            request.resolved_decay_profile.decay_per_second
            > component.resolved_decay_profile.decay_per_second
        )
        contributions = list(component.contributions)
        if amount_changed:
            new_contribution = AuraContribution(
                AuraContributionRef(self._next_contribution_ref())
                if previous is None
                else previous.contribution_ref,
                request.source_ref,
                amount,
                request.source_ref,
                request.frame if previous is None else previous.created_frame,
                request.frame,
                request.frame,
            )
            contributions = [
                item for item in contributions if item.contributor_ref != request.source_ref
            ] + [new_contribution]
        after = replace(
            component,
            contributions=tuple(contributions),
            decay_strength=(request.base_strength if profile_changed else component.decay_strength),
            decay_profile=(request.decay_profile if profile_changed else component.decay_profile),
            decay_origin=request.source_ref if profile_changed else component.decay_origin,
            last_applied_frame=request.frame,
            last_changed_frame=(
                request.frame if amount_changed or profile_changed else component.last_changed_frame
            ),
        )
        outcome = (
            AuraApplicationOutcome.AMOUNT_AND_PROFILE_UPDATED
            if amount_changed and profile_changed
            else AuraApplicationOutcome.AMOUNT_INCREASED
            if amount_changed
            else AuraApplicationOutcome.DECAY_PROFILE_UPGRADED
            if profile_changed
            else AuraApplicationOutcome.UNCHANGED
        )
        return (
            AuraApplicationResult(
                request.request_id,
                request.application_id,
                request.target_ref,
                aura_kind,
                outcome,
                component,
                after,
            ),
            after,
        )

    def _assert_open(self) -> None:
        if self._sealed:
            raise RuntimeError("AuraBatchPlanner 已封存")

    def _assert_request_identity(
        self,
        request_id: str,
        order: int,
        frame: int,
        request_kind: str,
    ) -> None:
        if frame != self.frame:
            raise ValueError(f"{request_kind}请求帧与所属批次不一致")
        if request_id in self._request_ids:
            raise ValueError(f"重复的 Aura request_id：{request_id}")
        if order in self._orders:
            raise ValueError(f"重复的 Aura order：{order}")

    def _next_instance_ref(self) -> str:
        self._instance_sequence += 1
        return f"aura-instance:{self._instance_sequence}"

    def _next_contribution_ref(self) -> str:
        self._contribution_sequence += 1
        return f"aura-contribution:{self._contribution_sequence}"


class AuraRuntime:
    def __init__(self) -> None:
        self._records: dict[ElementalSubjectRef, AuraTargetRecord] = {}
        self._version = 0
        self._normalized_through_frame = 0
        self._instance_sequence = 0
        self._contribution_sequence = 0
        self._committed_operation_ids: set[str] = set()
        self._committed_request_ids: set[str] = set()
        self._committed_interaction_ids: set[str] = set()
        self._fact_publication_active = False

    @property
    def version(self) -> int:
        return self._version

    @property
    def normalized_through_frame(self) -> int:
        return self._normalized_through_frame

    def view(self, subject_ref: ElementalSubjectRef) -> AuraView:
        record = self._records.get(subject_ref)
        return AuraView(
            subject_ref,
            () if record is None else record.components,
            0 if record is None else record.revision,
        )

    def begin_batch(self, frame: int, batch_id: str) -> AuraBatchPlanner:
        self._assert_write_allowed()
        if frame != self._normalized_through_frame:
            raise ValueError("Aura 批次要求所在帧已经完成规范化")
        return AuraBatchPlanner(self, frame, batch_id)

    def prepare_applications(
        self,
        requests: tuple[AuraApplicationRequest, ...],
    ) -> AuraMutationPlan:
        if not requests:
            return AuraMutationPlan(
                "aura:empty",
                self._normalized_through_frame,
                (),
                self.version,
                (),
                (),
            )
        planner = self.begin_batch(requests[0].frame, "applications:" + requests[0].request_id)
        for request in sorted(requests, key=lambda item: item.order):
            planner.apply(request)
        return planner.seal()

    def validate(self, plan: AuraMutationPlan) -> None:
        if plan.expected_store_version != self.version:
            raise AuraStoreConflictError("Aura 变更计划已经过期")
        if plan.operation_id in self._committed_operation_ids:
            raise AuraStoreConflictError("重复的 Aura 操作")
        duplicates = set(plan.request_ids) & self._committed_request_ids
        if duplicates:
            raise AuraStoreConflictError(f"重复的 Aura 请求：{sorted(duplicates)!r}")
        duplicate_interactions = set(plan.interaction_ids) & self._committed_interaction_ids
        if duplicate_interactions:
            raise AuraStoreConflictError(f"重复的 Aura 交互：{sorted(duplicate_interactions)!r}")
        if plan.frame != self._normalized_through_frame:
            raise AuraStoreConflictError("Aura 计划帧尚未规范化")

    def commit_prevalidated(self, plan: AuraMutationPlan) -> AuraCommitReceipt:
        self._assert_write_allowed()
        self.validate(plan)
        next_records = {record.subject_ref: record for record in plan.replacements}
        if next_records != self._records:
            self._records = next_records
            self._version += 1
        if plan.next_instance_sequence is not None:
            self._instance_sequence = plan.next_instance_sequence
        if plan.next_contribution_sequence is not None:
            self._contribution_sequence = plan.next_contribution_sequence
        self._committed_operation_ids.add(plan.operation_id)
        self._committed_request_ids.update(plan.request_ids)
        self._committed_interaction_ids.update(plan.interaction_ids)
        return AuraCommitReceipt(plan, self.version)

    def apply(self, request: AuraApplicationRequest) -> AuraApplicationResult:
        plan = self.prepare_applications((request,))
        self.commit_prevalidated(plan)
        return plan.application_results[0]

    def update_frame(self, context, frame: int) -> None:
        self._assert_write_allowed()
        if frame < self._normalized_through_frame:
            raise ValueError("Aura 帧不能回退")
        elapsed = frame - self._normalized_through_frame
        if elapsed == 0:
            return
        records: dict[ElementalSubjectRef, AuraTargetRecord] = {}
        depleted: list[AuraTransitionResult] = []
        changed = False
        for subject, record in self._records.items():
            components: list[AuraComponent] = []
            record_changed = False
            for component in record.components:
                if component.decay_mode is not AuraDecayMode.STANDARD:
                    components.append(component)
                    continue
                decay = component.resolved_decay_profile.decay_for_frames(elapsed)
                contributions = tuple(
                    replace(
                        contribution,
                        remaining_amount=(
                            contribution.remaining_amount
                            - decay.minimum(contribution.remaining_amount)
                        ),
                        last_changed_frame=frame,
                    )
                    for contribution in component.contributions
                    if contribution.remaining_amount > decay.minimum(contribution.remaining_amount)
                )
                if contributions:
                    components.append(
                        replace(
                            component,
                            contributions=contributions,
                            last_changed_frame=frame,
                        )
                    )
                else:
                    depleted.append(
                        AuraTransitionResult(
                            (
                                f"aura:depleted:{subject.kind.value}:"
                                f"{subject.entity_id}:{component.aura_kind.value}:{frame}"
                            ),
                            subject,
                            component.aura_kind,
                            component.current_amount,
                            component.current_amount,
                            AuraAmount.zero(),
                        )
                    )
                record_changed = record_changed or contributions != component.contributions
            if components:
                records[subject] = AuraTargetRecord(
                    subject,
                    tuple(components),
                    record.revision + int(record_changed),
                )
            changed = changed or record_changed
        self._records = records
        if changed:
            self._version += 1
        self._normalized_through_frame = frame
        if context is not None:
            with self.event_publication_guard():
                for result in depleted:
                    context.events.publish(
                        GameEvent(
                            EventType.AURA_DEPLETED,
                            frame,
                            AuraDepletedPayload(result),
                        )
                    )

    @contextmanager
    def event_publication_guard(self) -> Iterator[None]:
        """在 Aura 已提交事实发布期间拒绝新的 Aura 写入。"""

        if self._fact_publication_active:
            raise AuraEventPublicationError("Aura 领域事实发布不允许嵌套")
        self._fact_publication_active = True
        try:
            yield
        finally:
            self._fact_publication_active = False

    def _assert_write_allowed(self) -> None:
        if self._fact_publication_active:
            raise AuraEventPublicationError("Aura 领域事实发布期间不允许修改 Aura 状态")

    def snapshot(self) -> AuraSnapshot:
        return AuraSnapshot(
            self._normalized_through_frame,
            self._normalized_through_frame,
            tuple(
                sorted(
                    self._records.values(),
                    key=lambda item: (item.subject_ref.kind.value, item.subject_ref.entity_id),
                )
            ),
        )

    def is_idle(self) -> bool:
        return True


def _can_add_ordinary_aura(record: AuraTargetRecord, aura_kind: AuraKind) -> bool:
    frozen = record.component_for(AuraKind.FROZEN)
    if frozen is not None:
        return aura_kind in {AuraKind.HYDRO, AuraKind.CRYO} and len(record.components) == 1
    existing_kinds = frozenset(item.aura_kind for item in record.components)
    return existing_kinds | {aura_kind} in {
        frozenset({AuraKind.HYDRO, AuraKind.ELECTRO}),
        frozenset({AuraKind.DENDRO, AuraKind.CRYO}),
        frozenset({AuraKind.QUICKEN, AuraKind.PYRO}),
        frozenset({AuraKind.DENDRO, AuraKind.QUICKEN}),
        frozenset({AuraKind.DENDRO, AuraKind.QUICKEN, AuraKind.PYRO}),
        frozenset({AuraKind.BURNING, AuraKind.DENDRO, AuraKind.PYRO}),
    }
