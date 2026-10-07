"""阿罗夏内容 hook：印记施加、猎者之准授予、C1 回能与产球。"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_C1_ELECTRO_DIRECTION_MARKER,
    ALYOSHA_C1_ELECTRO_REACTION_KEYS,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
    ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_ATK_TERM_KEY,
    ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_TERM_KEY,
    ALYOSHA_HUNTERS_PRECISION_MECHANIC_KEY,
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
    ALYOSHA_PARTICLE_COOLDOWN_FRAMES,
    ALYOSHA_PARTICLE_COUNT,
    ALYOSHA_PARTICLE_ELEMENT,
    ALYOSHA_PARTICLE_SPAWN_IMPACT_KEY,
    ALYOSHA_PARTICLE_TRAVEL_FRAMES,
    ALYOSHA_PARTICLE_TRIGGER_IMPACT_KEYS,
    ALYOSHA_TEAM_SCOPE,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue
from genshin_sim.core.systems.buff.enums import BuffRemovalReason
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort

# 印记施加的触发影响键：NA4（官方文本：最后一击命中的敌人施加弋猎印记）与
# E 点按/长按（命中判定资料：附加「施加印记」标签）。命中判定按伤害事实实际
# 命中的敌人施加，AOE 展开与衰减不在此重复。
_MARK_APPLY_IMPACT_KEYS = (
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_IMPACT_KEY,
)

_ENEMY_TARGET_PREFIX = "target:"


def _require_positive_frames(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentUnitValidationError(f"{label} 必须是正整数帧数")
    return value


def _require_ratio(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0.0:
        raise ContentUnitValidationError(f"{label} 必须为正数")
    return float(value)


class AlyoshaMarkApplicationHook:
    """E 点按/NA4 命中施加弋猎印记（敌人侧标记 Buff，REPLACE 刷新）。"""

    def __init__(self, *, owner_ref: str, slot: int, mark_duration_frames: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("印记施加 hook owner_ref 必须是非空字符串")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._mark_duration_frames = _require_positive_frames(
            mark_duration_frames,
            "弋猎印记持续时间",
        )
        self.hook_key = f"alyosha.mark_apply:{owner_ref}"
        self.state_key = ALYOSHA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        target_ref = getattr(result, "target_ref", None)
        if not isinstance(target_ref, AttributeSubjectRef):
            return HookResult()
        target_id = getattr(target_ref, "entity_id", None)
        if (
            target_ref.kind is not AttributeSubjectKind.TARGET
            or not isinstance(target_id, str)
            or not target_id.startswith(_ENEMY_TARGET_PREFIX)
        ):
            return HookResult()
        request_id = getattr(result, "request_id", None)
        if not isinstance(request_id, str) or not any(
            key in request_id for key in _MARK_APPLY_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        return HookResult(
            buff_requests=(self._mark_request(frame, target_ref, 0),),
        )

    def _mark_request(
        self,
        frame: int,
        target_ref: AttributeSubjectRef,
        order: int,
    ) -> ApplyBuffRequest:
        return ApplyBuffRequest(
            request_id=f"{self.hook_key}:{frame}:{target_ref.entity_id}:mark",
            frame=frame,
            order=order,
            definition_key=ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
            target_ref=target_ref,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.MECHANIC,
                ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
            ),
            duration_frames=self._mark_duration_frames,
        )


class AlyoshaPrecisionGrantHook:
    """印记激活（清除）授予猎者之准：前台主体、随层叠加；C6 叠满伴生精通。

    猎者之准的攻击力提升值随 E 等级（组装期从资产倍率条目编译，hook 携带）；
    ``LINEAR`` 层数缩放使实际加成 = 每层值 × 当前层数。C6 下层数到达上限
    （2 层）时同帧伴生 +100 元素精通 Buff（REFRESH、与猎者之准同持续时间，
    随宿主猎者之准同帧刷新/到期）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        atk_bonus_per_stack: float,
        precision_duration_frames: int,
        precision_max_stacks: int,
        mastery_bonus: float | None,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("猎者之准授予 hook owner_ref 必须是非空字符串")
        self._owner_ref = owner_ref
        self._atk_bonus_per_stack = _require_ratio(atk_bonus_per_stack, "猎者之准攻击力提升")
        self._precision_duration_frames = _require_positive_frames(
            precision_duration_frames,
            "猎者之准持续时间",
        )
        if (
            isinstance(precision_max_stacks, bool)
            or not isinstance(precision_max_stacks, int)
            or precision_max_stacks <= 0
        ):
            raise ContentUnitValidationError("猎者之准最大层数必须是正整数")
        self._precision_max_stacks = precision_max_stacks
        self._mastery_bonus = (
            None
            if mastery_bonus is None
            else _require_ratio(
                mastery_bonus,
                "C6 猎者之准精通加成",
            )
        )
        self._team_subject_ref = AttributeSubjectRef.active_character(ALYOSHA_TEAM_SCOPE)
        self._precision_source_context = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            ALYOSHA_HUNTERS_PRECISION_MECHANIC_KEY,
        )
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.hook_key = f"alyosha.precision_grant:{owner_ref}"
        self.state_key = ALYOSHA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("BUFF_REMOVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配阶段原位绑定目标状态只读端口（C6 叠满判定读猎者之准层数）。"""

        self._target_status_port = target_status_port

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.BUFF_REMOVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "definition_key", None) != ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY:
            return HookResult()
        if getattr(result, "reason", None) is not BuffRemovalReason.CONSUMED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        requests: list[ApplyBuffRequest] = [
            ApplyBuffRequest(
                request_id=f"{self.hook_key}:{frame}:precision",
                frame=frame,
                order=0,
                definition_key=ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
                target_ref=self._team_subject_ref,
                source_context=self._precision_source_context,
                duration_frames=self._precision_duration_frames,
                modifier_values=(
                    BuffModifierValue(
                        ALYOSHA_HUNTERS_PRECISION_ATK_TERM_KEY,
                        self._atk_bonus_per_stack,
                    ),
                ),
            ),
        ]
        if self._mastery_bonus is not None and self._precision_full(frame):
            requests.append(
                ApplyBuffRequest(
                    request_id=f"{self.hook_key}:{frame}:mastery",
                    frame=frame,
                    order=1,
                    definition_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
                    target_ref=self._team_subject_ref,
                    source_context=self._precision_source_context,
                    duration_frames=self._precision_duration_frames,
                    modifier_values=(
                        BuffModifierValue(
                            ALYOSHA_HUNTERS_PRECISION_MASTERY_TERM_KEY,
                            self._mastery_bonus,
                        ),
                    ),
                ),
            )
        return HookResult(buff_requests=tuple(requests))

    def _precision_full(self, frame: int) -> bool:
        """本次授予后猎者之准是否到达层数上限（授予前层数 = 上限 - 1）。"""

        port = self._target_status_port
        if port is None:
            return False
        current = port.active_stack_count(
            target_ref=self._team_subject_ref,
            definition_key=ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
            frame=frame,
        )
        return current >= self._precision_max_stacks - 1


class AlyoshaC1EnergyHook:
    """C1 寒谷轰雷：雷元素相关反应为阿罗夏回复能量，18 秒内至多一次。

    可后台触发（不筛反应来源与触发者）；回能走 ``ImpactKind.ENERGY`` 的
    ``restore`` 出口，满能量时超额部分被能量系统按实际容量吞掉，触发照常
    计入冷却（不加满能量豁免）。触发间隔游标在 hook 实例。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        energy_amount: float,
        cooldown_frames: int,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C1 回能 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("C1 回能 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._slot = slot
        self._owner_target_ref = f"character:slot_{slot}"
        self._energy_amount = _require_ratio(energy_amount, "C1 回能")
        self._cooldown_frames = _require_positive_frames(cooldown_frames, "C1 回能冷却")
        self._last_proc_frame: int | None = None
        self.hook_key = f"alyosha.c1_energy:{owner_ref}"
        self.state_key = ALYOSHA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("REACTION_OCCURRED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        if getattr(event, "event_type", None) is not EventType.REACTION_OCCURRED:
            return HookResult()
        occurrence = getattr(getattr(event, "payload", None), "occurrence", None)
        if occurrence is None:
            return HookResult()
        if not self._is_electro_related(occurrence):
            return HookResult()
        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < self._cooldown_frames
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key="alyosha.c1_energy",
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    target_refs=(self._owner_target_ref,),
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "restore",
                            "amount": self._energy_amount,
                            "tags": (),
                        }
                    },
                ),
            ),
        )

    @staticmethod
    def _is_electro_related(occurrence: object) -> bool:
        """雷元素相关反应：恒涉雷的 reaction_key 或方向键携带雷方向。"""

        if getattr(occurrence, "reaction_key", None) in ALYOSHA_C1_ELECTRO_REACTION_KEYS:
            return True
        direction_key = getattr(occurrence, "direction_key", None)
        return isinstance(direction_key, str) and ALYOSHA_C1_ELECTRO_DIRECTION_MARKER in (
            direction_key
        )


class AlyoshaParticleHook:
    """产球：E 点按/长按伤害命中产 5 颗雷微粒，共用 0.5s 判定冷却。

    订阅 ``DAMAGE_RESOLVED``，按伤害实际结算帧判定；触发影响点按伤害结果
    ``request_id`` 内嵌的 impact_key 匹配（动作影响点 id 形如
    ``action:{instance_id}:{impact_key}``）。概率 100% 无需概率判定；冷却
    游标在 hook 实例，同帧多条命中事实即时去重。产球经 ``ImpactKind.ENERGY``
    的 ``spawn_pickup`` 出口，归属施放的阿罗夏（雷属性微粒）；轰霆猎场/
    图加林不产微粒。
    """

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"alyosha.particle:{owner_ref}"
        self.state_key = ALYOSHA_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 冷却游标在 hook 实例。
        if getattr(event, "event_type", None) is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if getattr(result, "source_ref", None) != self._owner_subject_ref:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        request_id = getattr(result, "request_id", None)
        if not isinstance(request_id, str) or not any(
            key in request_id for key in ALYOSHA_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < ALYOSHA_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=ALYOSHA_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": ALYOSHA_PARTICLE_ELEMENT.value,
                            "count": ALYOSHA_PARTICLE_COUNT,
                            "travel_frames": ALYOSHA_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
        )
