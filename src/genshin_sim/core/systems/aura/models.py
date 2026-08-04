"""Aura 领域值对象、不可变视图和变更计划。"""

from __future__ import annotations

from dataclasses import dataclass, field

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura.enums import (
    AuraApplicationOutcome,
    AuraDecayMode,
    AuraLossPolicy,
    AuraStrength,
)
from genshin_sim.core.systems.aura.profiles import AuraDecayProfile, profile_for


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _frame(value: int, name: str = "frame") -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, order=True, slots=True)
class AuraInstanceRef:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, "AuraInstanceRef")


@dataclass(frozen=True, order=True, slots=True)
class AuraContributionRef:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, "AuraContributionRef")


@dataclass(frozen=True, slots=True)
class AuraContribution:
    contribution_ref: AuraContributionRef
    contributor_ref: ElementalSourceRef
    remaining_amount: AuraAmount
    amount_origin: ElementalSourceRef
    created_frame: int
    last_effective_application_frame: int
    last_changed_frame: int

    def __post_init__(self) -> None:
        _frame(self.created_frame, "created_frame")
        _frame(self.last_effective_application_frame, "last_effective_application_frame")
        _frame(self.last_changed_frame, "last_changed_frame")


@dataclass(frozen=True, slots=True)
class AuraComponent:
    instance_ref: AuraInstanceRef
    aura_kind: AuraKind
    contributions: tuple[AuraContribution, ...]
    decay_strength: AuraStrength
    decay_origin: ElementalSourceRef
    created_frame: int
    last_applied_frame: int
    last_changed_frame: int
    state_link_refs: tuple[ElementalStateLinkRef, ...] = ()
    decay_mode: AuraDecayMode = AuraDecayMode.STANDARD
    decay_profile: AuraDecayProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.aura_kind, AuraKind):
            raise ValueError("不支持的 Aura 类型")
        if not isinstance(self.decay_strength, AuraStrength):
            raise ValueError("不支持的 AuraStrength")
        if not isinstance(self.decay_mode, AuraDecayMode):
            raise ValueError("不支持的 AuraDecayMode")
        if self.decay_profile is not None and not isinstance(self.decay_profile, AuraDecayProfile):
            raise ValueError("decay_profile 必须是 AuraDecayProfile 或 None")
        raw_state_link_refs = tuple(self.state_link_refs)
        if any(not isinstance(item, ElementalStateLinkRef) for item in raw_state_link_refs):
            raise ValueError("state_link_refs 必须是 ElementalStateLinkRef 序列")
        state_link_refs = tuple(sorted(raw_state_link_refs, key=lambda item: item.link_key))
        if len({item.link_key for item in state_link_refs}) != len(state_link_refs):
            raise ValueError("state_link_refs 不能包含重复 link_key")
        if self.aura_kind is AuraKind.FROZEN:
            if len(state_link_refs) != 1:
                raise ValueError("冻元素 AuraComponent 必须恰好携带一条 ElementalStateLinkRef")
            if self.decay_mode is not AuraDecayMode.STATE_LINKED:
                raise ValueError("冻元素必须由关联 ReactionState 驱动衰减")
            if self.decay_profile is not None:
                raise ValueError("冻元素 AuraComponent 不能携带自然衰减档案")
        elif self.aura_kind is AuraKind.BURNING:
            if len(state_link_refs) != 1:
                raise ValueError("燃元素 AuraComponent 必须恰好携带一条 ElementalStateLinkRef")
            if self.decay_mode is not AuraDecayMode.STATE_LINKED:
                raise ValueError("燃元素必须由关联 ReactionState 驱动衰减")
            if self.decay_profile is not None:
                raise ValueError("燃元素 AuraComponent 不能携带自然衰减档案")
        elif self.aura_kind is AuraKind.QUICKEN:
            if len(self.contributions) != 1:
                raise ValueError("激元素 AuraComponent 必须恰好保留一条派生贡献")
            if not state_link_refs:
                raise ValueError("激元素 AuraComponent 必须携带至少一条状态 Link")
            if self.decay_mode not in {AuraDecayMode.STANDARD, AuraDecayMode.REACTION_MANAGED}:
                raise ValueError("激元素只允许 STANDARD 或 REACTION_MANAGED 衰减模式")
            if self.decay_profile is None:
                raise ValueError("激元素 AuraComponent 必须携带精确自定义衰减档案")
        elif self.decay_mode is AuraDecayMode.REACTION_MANAGED:
            if self.aura_kind not in {AuraKind.DENDRO, AuraKind.QUICKEN} or not state_link_refs:
                raise ValueError("REACTION_MANAGED 仅允许带状态 Link 的普通草或激元素 Aura")
        elif self.decay_mode is AuraDecayMode.STATE_LINKED:
            raise ValueError("只有派生 Aura 可以使用 STATE_LINKED 衰减模式")
        contributions = tuple(
            sorted(self.contributions, key=lambda item: item.contribution_ref.value)
        )
        if not contributions:
            raise ValueError("AuraComponent 至少需要一条贡献")
        if any(item.remaining_amount.is_zero for item in contributions):
            raise ValueError("AuraComponent 不能保留元素量为零的贡献")
        object.__setattr__(self, "contributions", contributions)
        object.__setattr__(self, "state_link_refs", state_link_refs)
        _frame(self.created_frame, "created_frame")
        _frame(self.last_applied_frame, "last_applied_frame")
        _frame(self.last_changed_frame, "last_changed_frame")

    @property
    def current_amount(self) -> AuraAmount:
        return max(
            (item.remaining_amount for item in self.contributions),
            default=AuraAmount.zero(),
        )

    @property
    def resolved_decay_profile(self) -> AuraDecayProfile:
        return self.decay_profile or profile_for(self.decay_strength)

    def contribution_for(self, contributor_ref: ElementalSourceRef) -> AuraContribution | None:
        return next(
            (item for item in self.contributions if item.contributor_ref == contributor_ref),
            None,
        )

    @property
    def state_link_ref(self) -> ElementalStateLinkRef | None:
        """单 Link 调用方的过渡读取投影。"""

        return self.state_link_refs[0] if len(self.state_link_refs) == 1 else None


@dataclass(frozen=True, slots=True)
class AuraTargetRecord:
    subject_ref: ElementalSubjectRef
    components: tuple[AuraComponent, ...]
    revision: int = 0

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise ValueError("AuraTargetRecord revision 不能为负数")
        components = tuple(sorted(self.components, key=lambda item: item.aura_kind.value))
        if len({item.aura_kind for item in components}) != len(components):
            raise ValueError("每种 AuraKind 只能有一个活动 AuraComponent")
        frozen = tuple(item for item in components if item.aura_kind is AuraKind.FROZEN)
        ordinary = tuple(item for item in components if item.aura_kind is not AuraKind.FROZEN)
        ordinary_kinds = frozenset(item.aura_kind for item in ordinary)
        if frozen:
            if len(frozen) != 1 or ordinary_kinds not in {
                frozenset(),
                frozenset({AuraKind.HYDRO}),
                frozenset({AuraKind.CRYO}),
            }:
                raise ValueError("冻元素只允许单独存在或与一份藏水、藏冰共存")
        elif AuraKind.BURNING in ordinary_kinds:
            burning = next(item for item in ordinary if item.aura_kind is AuraKind.BURNING)
            dendro = next(
                (item for item in ordinary if item.aura_kind is AuraKind.DENDRO),
                None,
            )
            quicken = next(
                (item for item in ordinary if item.aura_kind is AuraKind.QUICKEN),
                None,
            )
            if (
                ordinary_kinds
                not in {
                    frozenset({AuraKind.BURNING, AuraKind.DENDRO}),
                    frozenset({AuraKind.BURNING, AuraKind.DENDRO, AuraKind.PYRO}),
                    frozenset({AuraKind.BURNING, AuraKind.QUICKEN}),
                    frozenset({AuraKind.BURNING, AuraKind.PYRO, AuraKind.QUICKEN}),
                    frozenset({AuraKind.BURNING, AuraKind.DENDRO, AuraKind.QUICKEN}),
                    frozenset({AuraKind.BURNING, AuraKind.DENDRO, AuraKind.PYRO, AuraKind.QUICKEN}),
                }
                or (dendro is None and quicken is None)
                or (dendro is not None and (
                    burning.state_link_refs[0] not in dendro.state_link_refs
                    or dendro.decay_mode is not AuraDecayMode.REACTION_MANAGED
                ))
                or (quicken is not None and (
                    burning.state_link_refs[0] not in quicken.state_link_refs
                    or quicken.decay_mode is not AuraDecayMode.REACTION_MANAGED
                ))
            ):
                raise ValueError("燃元素只能与受 Reaction 管理的关联类草及可选普通火共存")
        elif ordinary_kinds not in {
            frozenset(),
            frozenset({AuraKind.PYRO}),
            frozenset({AuraKind.HYDRO}),
            frozenset({AuraKind.ELECTRO}),
            frozenset({AuraKind.CRYO}),
            frozenset({AuraKind.DENDRO}),
            frozenset({AuraKind.DENDRO, AuraKind.PYRO}),
            frozenset({AuraKind.HYDRO, AuraKind.ELECTRO}),
            frozenset({AuraKind.DENDRO, AuraKind.CRYO}),
            frozenset({AuraKind.QUICKEN}),
            frozenset({AuraKind.QUICKEN, AuraKind.HYDRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.PYRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.DENDRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.DENDRO, AuraKind.PYRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.ELECTRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.CRYO}),
            frozenset({AuraKind.QUICKEN, AuraKind.DENDRO, AuraKind.ELECTRO}),
            frozenset({AuraKind.QUICKEN, AuraKind.DENDRO, AuraKind.CRYO}),
            frozenset({AuraKind.QUICKEN, AuraKind.ELECTRO, AuraKind.CRYO}),
            frozenset({AuraKind.QUICKEN, AuraKind.DENDRO, AuraKind.ELECTRO, AuraKind.CRYO}),
        }:
            raise ValueError("当前 Aura 不支持该普通元素 Component 组合")
        object.__setattr__(self, "components", components)

    def component_for(self, aura_kind: AuraKind) -> AuraComponent | None:
        return next((item for item in self.components if item.aura_kind is aura_kind), None)


@dataclass(frozen=True, slots=True)
class AuraView:
    subject_ref: ElementalSubjectRef
    components: tuple[AuraComponent, ...] = ()
    revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "components",
            tuple(sorted(self.components, key=lambda item: item.aura_kind.value)),
        )

    def component_for(self, aura_kind: AuraKind) -> AuraComponent | None:
        return next((item for item in self.components if item.aura_kind is aura_kind), None)


@dataclass(frozen=True, slots=True)
class AuraApplicationRequest:
    request_id: str
    application_id: str
    impact_ref: str
    frame: int
    order: int
    source_ref: ElementalSourceRef
    target_ref: ElementalSubjectRef
    element: Element
    base_strength: AuraStrength
    application_coefficient: AuraAmount = field(default_factory=AuraAmount.one)
    loss_policy: AuraLossPolicy = AuraLossPolicy.STANDARD_20_PERCENT
    effective_raw_amount: AuraAmount | None = None
    decay_profile: AuraDecayProfile | None = None

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.application_id, "application_id")
        _text(self.impact_ref, "impact_ref")
        _frame(self.frame)
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.element, Element):
            raise ValueError("不支持的 Element")
        if not isinstance(self.base_strength, AuraStrength):
            raise ValueError("不支持的 AuraStrength")
        if not isinstance(self.loss_policy, AuraLossPolicy):
            raise ValueError("不支持的 AuraLossPolicy")
        if self.effective_raw_amount is not None and self.effective_raw_amount.is_zero:
            raise ValueError("effective_raw_amount 提供时必须为正数")
        if self.decay_profile is not None:
            if not isinstance(self.decay_profile, AuraDecayProfile):
                raise ValueError("decay_profile 必须是 AuraDecayProfile 或 None")
            if self.effective_raw_amount != self.decay_profile.raw_amount:
                raise ValueError("decay_profile 必须与 effective_raw_amount 使用同一原始元素量")

    @property
    def resolved_decay_profile(self) -> AuraDecayProfile:
        return self.decay_profile or profile_for(self.base_strength)


@dataclass(frozen=True, slots=True)
class FrozenAuraApplicationRequest:
    """Reaction 计划创建或刷新派生冻元素的限定用途请求。"""

    request_id: str
    application_id: str
    impact_ref: str
    frame: int
    order: int
    source_ref: ElementalSourceRef
    target_ref: ElementalSubjectRef
    state_link_ref: ElementalStateLinkRef
    amount: AuraAmount
    replace_existing_amount: bool = False

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.application_id, "application_id")
        _text(self.impact_ref, "impact_ref")
        _frame(self.frame)
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.state_link_ref, ElementalStateLinkRef):
            raise ValueError("state_link_ref 必须是 ElementalStateLinkRef")
        if not isinstance(self.amount, AuraAmount) or self.amount.is_zero:
            raise ValueError("冻元素 amount 必须是正的 AuraAmount")
        if not isinstance(self.replace_existing_amount, bool):
            raise ValueError("replace_existing_amount 必须是布尔值")


@dataclass(frozen=True, slots=True)
class BurningAuraApplicationRequest:
    """Reaction 计划创建或刷新派生燃元素的限定用途请求。"""

    request_id: str
    application_id: str
    impact_ref: str
    frame: int
    order: int
    source_ref: ElementalSourceRef
    target_ref: ElementalSubjectRef
    state_link_ref: ElementalStateLinkRef
    amount: AuraAmount
    replace_existing_amount: bool = False

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.application_id, "application_id")
        _text(self.impact_ref, "impact_ref")
        _frame(self.frame)
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.state_link_ref, ElementalStateLinkRef):
            raise ValueError("state_link_ref 必须是 ElementalStateLinkRef")
        if not isinstance(self.amount, AuraAmount) or self.amount.is_zero:
            raise ValueError("燃元素 amount 必须是正的 AuraAmount")
        if not isinstance(self.replace_existing_amount, bool):
            raise ValueError("replace_existing_amount 必须是布尔值")


@dataclass(frozen=True, slots=True)
class BurningAuraEstablishmentRequest:
    """燃烧首次成立时普通后手 Aura 与派生燃元素的原子写入请求。"""

    incoming_application: AuraApplicationRequest
    burning_application: BurningAuraApplicationRequest

    def __post_init__(self) -> None:
        incoming = self.incoming_application
        burning = self.burning_application
        if not isinstance(incoming, AuraApplicationRequest):
            raise ValueError("incoming_application 必须是 AuraApplicationRequest")
        if not isinstance(burning, BurningAuraApplicationRequest):
            raise ValueError("burning_application 必须是 BurningAuraApplicationRequest")
        if incoming.element not in {Element.PYRO, Element.DENDRO}:
            raise ValueError("燃烧首次成立的后手元素必须是火或草")
        if incoming.loss_policy is not AuraLossPolicy.STANDARD_20_PERCENT:
            raise ValueError("燃烧首次成立的后手元素必须使用标准 20% Aura 损耗")
        if incoming.frame != burning.frame or incoming.target_ref != burning.target_ref:
            raise ValueError("燃烧首次成立的 Aura 请求必须使用同一帧和主体")
        if incoming.source_ref != burning.source_ref:
            raise ValueError("燃烧首次成立的 Aura 请求必须使用同一来源")
        if incoming.request_id == burning.request_id or incoming.order == burning.order:
            raise ValueError("燃烧首次成立的两个 Aura 请求必须使用不同 identity")
        if burning.amount != AuraAmount(2) or burning.replace_existing_amount:
            raise ValueError("燃烧首次成立必须创建不可刷新的固定 2 GU 燃元素")


@dataclass(frozen=True, slots=True)
class QuickenAuraApplicationRequest:
    """Reaction 强类型计划创建或取大覆盖派生激元素的限定用途请求。"""

    request_id: str
    application_id: str
    impact_ref: str
    frame: int
    order: int
    source_ref: ElementalSourceRef
    target_ref: ElementalSubjectRef
    state_link_ref: ElementalStateLinkRef
    amount: AuraAmount
    contribution_ref: AuraContributionRef

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _text(self.application_id, "application_id")
        _text(self.impact_ref, "impact_ref")
        _frame(self.frame)
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.state_link_ref, ElementalStateLinkRef):
            raise ValueError("state_link_ref 必须是 ElementalStateLinkRef")
        if not isinstance(self.amount, AuraAmount) or self.amount.is_zero:
            raise ValueError("激元素 amount 必须是正的 AuraAmount")
        if not isinstance(self.contribution_ref, AuraContributionRef):
            raise ValueError("contribution_ref 必须是 AuraContributionRef")


@dataclass(frozen=True, slots=True)
class AuraStateLinkMutationRequest:
    """同一 AuraComponent 的状态 Link 与衰减模式变更。"""

    request_id: str
    frame: int
    order: int
    target_ref: ElementalSubjectRef
    aura_kind: AuraKind
    add_link_refs: tuple[ElementalStateLinkRef, ...] = ()
    remove_link_refs: tuple[ElementalStateLinkRef, ...] = ()
    decay_mode: AuraDecayMode | None = None

    def __post_init__(self) -> None:
        _text(self.request_id, "request_id")
        _frame(self.frame)
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order 必须是非负整数")
        if not isinstance(self.aura_kind, AuraKind):
            raise ValueError("aura_kind 必须是 AuraKind")
        if self.decay_mode is not None and not isinstance(self.decay_mode, AuraDecayMode):
            raise ValueError("decay_mode 必须是 AuraDecayMode 或 None")
        for links, name in (
            (self.add_link_refs, "add_link_refs"),
            (self.remove_link_refs, "remove_link_refs"),
        ):
            if any(not isinstance(item, ElementalStateLinkRef) for item in links):
                raise ValueError(f"{name} 必须是 ElementalStateLinkRef 序列")
            if len({item.link_key for item in links}) != len(links):
                raise ValueError(f"{name} 不能包含重复 link_key")
        if not self.add_link_refs and not self.remove_link_refs and self.decay_mode is None:
            raise ValueError("Link 变更请求至少需要一项变更")
        if set(self.add_link_refs) & set(self.remove_link_refs):
            raise ValueError("同一 Link 不能在一个请求中同时添加和删除")


@dataclass(frozen=True, slots=True)
class AuraApplicationResult:
    request_id: str
    application_id: str
    subject_ref: ElementalSubjectRef
    aura_kind: AuraKind
    outcome: AuraApplicationOutcome
    before: AuraComponent | None
    after: AuraComponent | None


@dataclass(frozen=True, slots=True)
class AuraTransitionResult:
    interaction_id: str
    subject_ref: ElementalSubjectRef
    aura_kind: AuraKind
    amount_before: AuraAmount
    amount_consumed: AuraAmount
    amount_after: AuraAmount


@dataclass(frozen=True, slots=True)
class AuraMutationPlan:
    operation_id: str
    frame: int
    request_ids: tuple[str, ...]
    expected_store_version: int
    replacements: tuple[AuraTargetRecord, ...]
    removed_subject_refs: tuple[ElementalSubjectRef, ...]
    application_results: tuple[AuraApplicationResult, ...] = ()
    transition_results: tuple[AuraTransitionResult, ...] = ()
    interaction_ids: tuple[str, ...] = ()
    next_instance_sequence: int | None = None
    next_contribution_sequence: int | None = None

    def __post_init__(self) -> None:
        interaction_ids = tuple(self.interaction_ids)
        if any(not isinstance(item, str) or not item.strip() for item in interaction_ids):
            raise ValueError("interaction_ids 必须是非空字符串序列")
        if len(set(interaction_ids)) != len(interaction_ids):
            raise ValueError("AuraMutationPlan 的 interaction_ids 不能重复")
        object.__setattr__(self, "interaction_ids", interaction_ids)
        for value, name in (
            (self.next_instance_sequence, "next_instance_sequence"),
            (self.next_contribution_sequence, "next_contribution_sequence"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} 必须是非负整数或 None")


@dataclass(frozen=True, slots=True)
class AuraCommitReceipt:
    plan: AuraMutationPlan
    version: int


@dataclass(frozen=True, slots=True)
class AuraSnapshot:
    frame: int
    normalized_through_frame: int
    targets: tuple[AuraTargetRecord, ...]
