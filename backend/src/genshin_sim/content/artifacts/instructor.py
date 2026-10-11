"""教官圣遗物套装实现。

资产数据来源：Project Amber / Yatta 当前默认数据（``artifact_set:10007``）；
套装命名采用官方英文名 Instructor（meropide.cn/en/artifacts）。

效果与落点：

- 2 件套：元素精通提高 80 点 -> ``stat.elemental_mastery``
  ``flat_add``，静态绑定穿戴者。
- 4 件套：触发元素反应后，队伍中所有角色的元素精通提高 120 点，持续
  8 秒 -> 全队 ``stat.elemental_mastery`` ``flat_add`` Buff，480 帧。

行为约定：

- 4 件套以 ``REACTION_OCCURRED`` 事实承接：文案不限定触发者，任何
  元素反应（含穿戴者处于后台时他人触发的反应）都会开启窗口。
- 文案没有「不可叠加」条款：不同穿戴者的 4 件套效果按槽位独立定义、
  可同时存在并叠加（与少女 4 件套同一约定）；同一穿戴者的重复触发
  按刷新处理。
- 触发不区分反应种类：文案只说「触发元素反应」，不做反应白名单。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.models import HookResult
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.systems.buff import (
    ApplyBuffRequest,
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)

INSTRUCTOR_KEY_PREFIX = "artifact.instructor"
INSTRUCTOR_HANDLER_KEY = INSTRUCTOR_KEY_PREFIX
INSTRUCTOR_2P_HANDLER_KEY = f"{INSTRUCTOR_KEY_PREFIX}.2p"
INSTRUCTOR_4P_HANDLER_KEY = f"{INSTRUCTOR_KEY_PREFIX}.4p"
INSTRUCTOR_CONTENT_VERSION = "release"

INSTRUCTOR_2P_AUDIT_TAG = "instructor_2p"
INSTRUCTOR_4P_AUDIT_TAG = "instructor_4p"

FRAMES_PER_SECOND = 60

INSTRUCTOR_4P_TERM_KEY = f"{INSTRUCTOR_KEY_PREFIX}.4p.elemental_mastery"


def instructor_4p_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的 Buff 定义键。"""

    return f"{INSTRUCTOR_KEY_PREFIX}.4p.elemental_mastery.slot:{slot}"


def instructor_4p_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的冲突键，保证不同穿戴者独立叠加。"""

    return f"{INSTRUCTOR_KEY_PREFIX}.4p.slot:{slot}"


def create_instructor_identity_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """教官套装身份单元：表明这个套装是什么，并拥有它的件数效果单元。"""

    _require_set_row(request, handler_key=INSTRUCTOR_HANDLER_KEY)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=INSTRUCTOR_HANDLER_KEY,
        version=INSTRUCTOR_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "instructor_set_identity"},
    )


def create_instructor_two_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """教官 2 件套：元素精通提高。"""

    _require_piece_count(
        request,
        expected=2,
        handler_key=INSTRUCTOR_2P_HANDLER_KEY,
    )
    (mastery_flat,) = _parse_component_values(
        request.params,
        count=1,
        purpose="2 件套元素精通加成",
    )
    subject_ref = AttributeSubjectRef.character(_owner_ref(request.slot))
    provider_key = f"{INSTRUCTOR_KEY_PREFIX}.2p.mastery.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ELEMENTAL_MASTERY}),
            owner_ref=subject_ref,
            display_name="教官 2件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
                value=mastery_flat,
                provider_key=provider_key,
                source_ref=_source_ref("2p", request.slot),
                audit_tags=(INSTRUCTOR_2P_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=INSTRUCTOR_2P_HANDLER_KEY,
        version=INSTRUCTOR_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "instructor_2p"},
    )


def create_instructor_four_piece_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """教官 4 件套：触发元素反应后全队元素精通提升。"""

    _require_piece_count(
        request,
        expected=4,
        handler_key=INSTRUCTOR_4P_HANDLER_KEY,
    )
    mastery_flat, duration_seconds = _parse_component_values(
        request.params,
        count=2,
        purpose="4 件套元素精通加成/持续时间",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = _owner_ref(request.slot)
    definition_key = instructor_4p_definition_key(request.slot)
    hook = InstructorReactionHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        mastery_bonus=mastery_flat,
        definition_key=definition_key,
        term_key=INSTRUCTOR_4P_TERM_KEY,
    )
    definition = _build_party_mastery_buff_definition(definition_key, request.slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=INSTRUCTOR_4P_HANDLER_KEY,
        version=INSTRUCTOR_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "instructor_4p"},
    )


def _build_party_mastery_buff_definition(
    definition_key: str,
    slot: int,
) -> BuffDefinition:
    """4 件套全队元素精通 Buff 定义；按槽位区分，不同穿戴者独立叠加。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{INSTRUCTOR_KEY_PREFIX}.4p.elemental_mastery",
        handler_key=INSTRUCTOR_4P_HANDLER_KEY,
        conflict_key=instructor_4p_conflict_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="教官 4件套",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=INSTRUCTOR_4P_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
                audit_tags=(INSTRUCTOR_4P_AUDIT_TAG,),
            ),
        ),
    )


class InstructorReactionHook:
    """4 件套：任意元素反应触发后为全队施加元素精通 Buff。

    不做触发者归属过滤：文案不限定触发者，穿戴者处于后台同样成立。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        mastery_bonus: float,
        definition_key: str,
        term_key: str,
    ) -> None:
        if duration_frames <= 0:
            raise ContentUnitValidationError("4 件套持续时间必须是正帧数")
        if not math.isfinite(mastery_bonus) or mastery_bonus <= 0:
            raise ContentUnitValidationError("4 件套元素精通加成必须为正数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._mastery_bonus = mastery_bonus
        self._definition_key = definition_key
        self._term_key = term_key
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.CONTENT,
            f"{INSTRUCTOR_KEY_PREFIX}:4p:slot:{slot}",
        )
        self.hook_key = f"{INSTRUCTOR_4P_HANDLER_KEY}:{owner_ref}"
        self.state_key = INSTRUCTOR_4P_HANDLER_KEY
        self.subscriptions = ("REACTION_OCCURRED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        payload = getattr(event, "payload", None)
        if payload is None or getattr(payload, "occurrence", None) is None:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        team_state = getattr(context, "states", None)
        characters = tuple(getattr(team_state, "characters", ()))
        if not characters:
            return HookResult()
        requests = tuple(
            ApplyBuffRequest(
                request_id=f"hook:{self.hook_key}:{frame}:{character.combat_entity_id}",
                frame=frame,
                order=index,
                definition_key=self._definition_key,
                target_ref=AttributeSubjectRef.character(character.combat_entity_id),
                source_context=self._source_ref,
                duration_frames=self._duration_frames,
                applier_ref=self._owner_subject_ref,
                modifier_values=(
                    BuffModifierValue(
                        term_key=self._term_key,
                        value=self._mastery_bonus,
                    ),
                ),
            )
            for index, character in enumerate(characters)
        )
        return HookResult(buff_requests=requests)


def _require_piece_count(
    request: ArtifactContentUnitRequest,
    *,
    expected: int,
    handler_key: str,
) -> None:
    """件数效果键必须绑定到对应件数的效果行。"""

    if request.piece_count != expected:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定 {expected} 件套效果，收到 {request.piece_count} 件"
        )


def _require_set_row(request: ArtifactContentUnitRequest, *, handler_key: str) -> None:
    """套装索引行单元键只能绑定套装索引行，不能绑定件数效果行。"""

    if request.piece_count is not None:
        raise ContentUnitValidationError(
            f"{handler_key} 只绑定套装索引行，收到 {request.piece_count} 件套效果行"
        )


def _owner_ref(slot: int) -> str:
    return f"character:slot_{slot}"


def _source_ref(scope: str, slot: int) -> RuntimeSourceRef:
    return RuntimeSourceRef(
        RuntimeSourceKind.CONTENT,
        f"{INSTRUCTOR_KEY_PREFIX}:{scope}:slot:{slot}",
    )


def _parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取数值列表（与正式内容 components 约定一致）。"""

    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes))
        or len(components) < count
    ):
        raise ContentUnitValidationError(f"{purpose} 缺少 components 参数")
    values: list[float] = []
    for index in range(count):
        component = components[index]
        if not isinstance(component, Mapping):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 必须是对象")
        raw_values = component.get("values")
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes))
            or not raw_values
        ):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 缺少 values")
        value = raw_values[0]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须是数字")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
