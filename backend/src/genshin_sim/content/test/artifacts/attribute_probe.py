"""属性探针套装：静态与动态属性 Buff（角色状态详情验证用合成内容）。

- 2 件套：固定防御力百分比加成，静态绑定穿戴者。
- 4 件套：穿戴者开始任意动作后，为自身施加持续 10 秒的攻击力百分比
  Buff，重复触发按刷新处理。合成触发条件只为便于手动演示，不代表任何
  真实套装机制。

所有数值均为测试固定值，不代表任何真实游戏数据。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.models import HookResult
from genshin_sim.content.registries import ArtifactContentUnitRequest
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_DEF_TOTAL,
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

ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY = "artifact.testing.attribute_probe"
ATTRIBUTE_PROBE_ARTIFACT_ASSET_KEY = "artifact_set:test_attribute_probe"
ATTRIBUTE_PROBE_ARTIFACT_CONTENT_VERSION = "dev-attribute-probe-artifact"

ATTRIBUTE_PROBE_4P_TERM_KEY = f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.4p.atk"
ATTRIBUTE_PROBE_4P_MECHANIC_KEY = f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.4p.atk_buff"

FRAMES_PER_SECOND = 60


def attribute_probe_4p_definition_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的 Buff 定义键。"""

    return f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.4p.atk.slot:{slot}"


def attribute_probe_4p_conflict_key(slot: int) -> str:
    """4 件套按穿戴者槽位区分的冲突键。"""

    return f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.4p.conflict.slot:{slot}"


class AttributeProbeFourPieceBuffHook:
    """4 件套：穿戴者开始动作后为自身施加攻击力 Buff。"""

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        duration_frames: int,
        atk_bonus: float,
        definition_key: str,
        source_key: str,
    ) -> None:
        self._owner_ref = owner_ref
        self._slot = slot
        self._duration_frames = duration_frames
        self._atk_bonus = atk_bonus
        self._definition_key = definition_key
        self._source_key = source_key
        self.hook_key = f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.4p:{owner_ref}"
        self.state_key = ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY
        self.subscriptions = ("ACTION_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        payload = getattr(event, "payload", None)
        if payload is None or getattr(payload, "owner_slot", None) != self._slot:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        instance_id = getattr(payload, "instance_id", None)
        instance_suffix = (
            str(instance_id)
            if isinstance(instance_id, int) and not isinstance(instance_id, bool)
            else frame
        )
        owner_ref = AttributeSubjectRef.character(self._owner_ref)
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{instance_suffix}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=owner_ref,
                    applier_ref=owner_ref,
                    source_context=RuntimeSourceRef(
                        RuntimeSourceKind.CONTENT,
                        self._source_key,
                    ),
                    duration_frames=self._duration_frames,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=ATTRIBUTE_PROBE_4P_TERM_KEY,
                            value=self._atk_bonus,
                        ),
                    ),
                ),
            )
        )


def create_attribute_probe_artifact_content_unit(
    request: ArtifactContentUnitRequest,
) -> ContentUnit:
    """属性探针套装内容单元工厂（按件数分支）。"""

    if request.artifact_key != ATTRIBUTE_PROBE_ARTIFACT_ASSET_KEY:
        raise ContentUnitValidationError(
            f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY!r} 只绑定 "
            f"{ATTRIBUTE_PROBE_ARTIFACT_ASSET_KEY}，收到 {request.artifact_key!r}"
        )
    if request.artifact_kind != "artifact_set_bonus":
        raise ContentUnitValidationError(
            f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY} 只绑定套装效果，不绑定套装行"
        )
    if request.piece_count == 2:
        return _create_two_piece_unit(request)
    if request.piece_count == 4:
        return _create_four_piece_unit(request)
    raise ContentUnitValidationError(
        f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY} 不支持 {request.piece_count} 件套"
    )


def _create_two_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    (def_percent,) = _parse_component_values(
        request.params,
        count=1,
        purpose="属性探针 2 件套防御加成",
    )
    owner_ref = AttributeSubjectRef.character(f"character:slot_{request.slot}")
    provider_key = f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}.2p.def_percent.slot:{request.slot}"
    provider = StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_DEF_TOTAL}),
            owner_ref=owner_ref,
            display_name="属性探针套装 2 件套",
        ),
        (
            ModifierTerm(
                target_key=STAT_DEF_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=def_percent,
                provider_key=provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}:2p:slot:{request.slot}",
                ),
                audit_tags=("attribute_probe_2p_def_percent",),
            ),
        ),
        subject_ref=owner_ref,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY,
        version=ATTRIBUTE_PROBE_ARTIFACT_CONTENT_VERSION,
        slot=request.slot,
        attribute_providers=(provider,),
        metadata={"piece_count": 2, "purpose": "testing_attribute_probe_2p"},
    )


def _create_four_piece_unit(request: ArtifactContentUnitRequest) -> ContentUnit:
    duration_seconds, atk_percent = _parse_component_values(
        request.params,
        count=2,
        purpose="属性探针 4 件套攻击 Buff",
    )
    duration_frames = round(duration_seconds * FRAMES_PER_SECOND)
    if duration_frames <= 0:
        raise ContentUnitValidationError("4 件套持续时间必须折算为正帧数")
    owner_ref = f"character:slot_{request.slot}"
    definition_key = attribute_probe_4p_definition_key(request.slot)
    hook = AttributeProbeFourPieceBuffHook(
        owner_ref=owner_ref,
        slot=request.slot,
        duration_frames=duration_frames,
        atk_bonus=atk_percent,
        definition_key=definition_key,
        source_key=f"{ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY}:4p:slot:{request.slot}",
    )
    definition = BuffDefinition(
        definition_key=definition_key,
        mechanic_key=ATTRIBUTE_PROBE_4P_MECHANIC_KEY,
        handler_key=ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY,
        conflict_key=attribute_probe_4p_conflict_key(request.slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REPLACE,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="属性探针套装 4 件套·攻击提升",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=ATTRIBUTE_PROBE_4P_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                audit_tags=("attribute_probe_4p_atk_percent",),
            ),
        ),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key=request.artifact_key,
        handler_key=ATTRIBUTE_PROBE_ARTIFACT_HANDLER_KEY,
        version=ATTRIBUTE_PROBE_ARTIFACT_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(hook,),
        buff_definitions=(definition,),
        metadata={"piece_count": 4, "purpose": "testing_attribute_probe_4p"},
    )


def _parse_component_values(
    params: Mapping[str, object],
    *,
    count: int,
    purpose: str,
) -> tuple[float, ...]:
    """从套装效果 params 读取前 ``count`` 个数值。"""

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
        if number <= 0:
            raise ContentUnitValidationError(f"{purpose} components[{index}] 数值必须为正数")
        values.append(number)
    return tuple(values)
