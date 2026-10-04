"""奥黛塔内容事件钩子：产球、C2 减抗光环与 C4 协同攻击。

产球（维护者提供的角色产球表）：战技技能伤害命中或破晓终奏持续命中产
5 冰微粒（100% 概率、共用 12s 判定冷却），触发面与命中表「元素战技掉球」
附加标签的命中一致（E 初始段 + 破晓终奏持续三段；Q 与舞步不产球）。
触发影响点按伤害结果 ``request_id`` 内嵌的 impact_key 匹配；冷却游标在
hook 实例，最近产球帧同步写入内容状态 ``odette_last_particle_frame`` 供
审计（0 表示尚未产球）。产球经 ``ImpactKind.ENERGY`` 的 ``spawn_pickup``
出口，归属宿主奥黛塔（冰属性微粒）。

C2 减抗光环：`FRAME_STARTED` 每 60 帧判定一次，条件为「独舞
倒影在场 ∧ 奥黛塔处于辉映·星烁」；满足时给倒影附近敌人应用对应变体的减抗
Buff（辉映·星超导：冰+雷；辉映·星扩散：冰+风），并把另一变体的残留显式
移除——同一目标任意时刻至多一条该光环实例。

C4 协同攻击：订阅 ``DAMAGE_RESOLVED``，**队伍中任意角色**造成星烁反应伤害
命中敌人时排队一次协同攻击，在触发后第 5 帧
落地，变体按**落地时**奥黛塔的辉映状态分派（无辉映证据时走星超导变体）；
内置冷却 210f 由实例游标承担，排队帧与目标同样记在实例（短生命周期，与
``_last_proc_frame`` 同口径）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from genshin_sim.content.characters.snezhnaya.odette.dance import active_dance_reflection
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_C2_AURA_DURATION_FRAMES,
    ODETTE_C2_AURA_IMPACT_KEY,
    ODETTE_C2_AURA_RADIUS,
    ODETTE_C2_CHECK_INTERVAL_FRAMES,
    ODETTE_C2_CONDUCT_VARIANT,
    ODETTE_C2_SWIRL_VARIANT,
    ODETTE_C4_COORDINATED_DELAY_FRAMES,
    ODETTE_C4_COORDINATED_DISPLAY_NAME,
    ODETTE_C4_COORDINATED_IMPACT_KEY,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_PARTICLE_COOLDOWN_FRAMES,
    ODETTE_PARTICLE_COUNT,
    ODETTE_PARTICLE_ELEMENT,
    ODETTE_PARTICLE_SPAWN_IMPACT_KEY,
    ODETTE_PARTICLE_TRAVEL_FRAMES,
    ODETTE_PARTICLE_TRIGGER_IMPACT_KEYS,
    ODETTE_STATE_LAST_PARTICLE_FRAME,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    STELLAR_REACTION_DAMAGE_TAGS,
    OdetteStellarChannel,
    RadianceVariant,
    radiance_evidence,
    resolve_stellar_variant_spec,
    stellar_variant_hit,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.hooks import HookContext
from genshin_sim.content.models import HookResult
from genshin_sim.content.state_container import StatePatchRequest
from genshin_sim.core.attributes import AttributeSubjectKind, AttributeSubjectRef
from genshin_sim.core.entity_states.targets import TargetRuntimeState
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ImpactKind, ImpactRequest, StrikeType
from genshin_sim.core.space import CreatedObjectRuntimeState, SpatialEntityKind
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)

# 敌方目标判据按 entity_id 前缀区分（与西风系列武器钩子同口径）。
_ENEMY_TARGET_PREFIX = "target:"


class OdetteParticleHook:
    """产球：战技技能伤害与破晓终奏持续命中产 5 冰微粒，共用 12s 判定冷却。"""

    def __init__(self, *, owner_ref: str, slot: int) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("产球 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("产球 hook 必须绑定正整数队伍槽位")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._last_proc_frame: int | None = None
        self.hook_key = f"odette.particle:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        """宿主角色引用：状态段归属校验按此匹配。"""

        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context  # 冷却游标在 hook 实例；内容状态字段随产出同步写入。
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
            key in request_id for key in ODETTE_PARTICLE_TRIGGER_IMPACT_KEYS
        ):
            return HookResult()

        frame = getattr(event, "frame", 0)
        if (
            self._last_proc_frame is not None
            and frame - self._last_proc_frame < ODETTE_PARTICLE_COOLDOWN_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=ODETTE_PARTICLE_SPAWN_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=f"hook:{self.hook_key}:{frame}",
                    params={
                        "energy": {
                            "schema_version": 1,
                            "operation": "spawn_pickup",
                            "pickup_kind": "particle",
                            "element": ODETTE_PARTICLE_ELEMENT.value,
                            "count": ODETTE_PARTICLE_COUNT,
                            "travel_frames": ODETTE_PARTICLE_TRAVEL_FRAMES,
                            "tags": (),
                        }
                    },
                ),
            ),
            state_patches=(
                StatePatchRequest(
                    owner_ref=self._owner_ref,
                    state_key=self.state_key,
                    fields={ODETTE_STATE_LAST_PARTICLE_FRAME: frame},
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ResistanceAuraVariantSpec:
    """C2 减抗光环的一个变体：定义键与完整词条值（与定义模板一一对应）。"""

    definition_key: str
    modifier_values: tuple[dict[str, object], ...]


class OdetteC2ResistanceHook:
    """C2 减抗光环：每 60 帧给独舞倒影附近的敌人应用对应变体的元素减抗。

    条件（独舞倒影在场 ∧ 奥黛塔持辉映·星烁）不成立时，两个变体都从全部目标
    上显式移除；成立时只保留当前变体（先移除另一变体残留）。「附近」半径见
    ``data.py`` 的实现基线说明。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        variants: dict[str, ResistanceAuraVariantSpec],
        radius: float = ODETTE_C2_AURA_RADIUS,
        interval_frames: int = ODETTE_C2_CHECK_INTERVAL_FRAMES,
        duration_frames: int = ODETTE_C2_AURA_DURATION_FRAMES,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C2 减抗光环 hook owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("C2 减抗光环 hook 必须绑定正整数队伍槽位")
        missing = [
            variant
            for variant in (ODETTE_C2_CONDUCT_VARIANT, ODETTE_C2_SWIRL_VARIANT)
            if variant not in variants
        ]
        if missing:
            raise ContentUnitValidationError(f"C2 减抗光环缺少变体定义：{missing}")
        if radius <= 0.0:
            raise ContentUnitValidationError("C2 减抗光环半径必须为正数")
        if interval_frames <= 0 or duration_frames <= 0:
            raise ContentUnitValidationError("C2 减抗光环判定周期与期限必须是正帧数")
        self._owner_ref = owner_ref
        self._slot = slot
        self._variants = dict(variants)
        self._radius = radius
        self._interval_frames = interval_frames
        self._duration_frames = duration_frames
        self.hook_key = f"odette.c2:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("FRAME_STARTED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        if getattr(event, "event_type", None) is not EventType.FRAME_STARTED:
            return HookResult()
        frame = getattr(event, "frame", 0)
        if frame <= 0 or frame % self._interval_frames != 0:
            return HookResult()
        hook_context = cast(HookContext, context)
        target_refs = self._all_target_refs(hook_context)
        if not target_refs:
            return HookResult()

        summon = active_dance_reflection(hook_context.simulation, self._slot)
        active_variant = None if summon is None else self._active_variant(hook_context, frame)
        requests: list[ImpactRequest] = []
        for variant in sorted(self._variants):
            if variant == active_variant:
                continue
            requests.append(self._remove_request(frame, variant, tuple(target_refs)))
        if active_variant is not None and summon is not None:
            in_range = self._target_refs_in_radius(hook_context, summon)
            if in_range:
                requests.append(self._apply_request(frame, active_variant, in_range))
        if not requests:
            return HookResult()
        return HookResult(impact_requests=tuple(requests))

    def _active_variant(self, hook_context: HookContext, frame: int) -> str | None:
        evidence = radiance_evidence(hook_context.simulation, self._owner_ref, frame)
        if evidence is None:
            return None
        return (
            ODETTE_C2_CONDUCT_VARIANT
            if evidence.variant is RadianceVariant.CONDUCT
            else ODETTE_C2_SWIRL_VARIANT
        )

    def _apply_request(
        self,
        frame: int,
        variant: str,
        target_refs: tuple[str, ...],
    ) -> ImpactRequest:
        spec = self._variants[variant]
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.APPLY_STATUS,
            impact_key=ODETTE_C2_AURA_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{frame}:{variant}",
            target_refs=target_refs,
            params={
                "buff": {
                    "definition_key": spec.definition_key,
                    "duration_frames": self._duration_frames,
                    "stack_delta": 1,
                    "modifier_values": spec.modifier_values,
                    "applier_ref": AttributeSubjectRef.character(self._owner_ref).to_dict(),
                },
            },
        )

    def _remove_request(
        self, frame: int, variant: str, target_refs: tuple[str, ...]
    ) -> ImpactRequest:
        return ImpactRequest(
            frame=frame,
            kind=ImpactKind.REMOVE_STATUS,
            impact_key=ODETTE_C2_AURA_IMPACT_KEY,
            owner_slot=self._slot,
            request_id=f"hook:{self.hook_key}:{frame}:clear:{variant}",
            target_refs=target_refs,
            params={
                "buff_remove": {"definition_key": self._variants[variant].definition_key},
            },
        )

    def _all_target_refs(self, hook_context: HookContext) -> tuple[str, ...]:
        return tuple(target.spatial_entity_id for target in self._targets(hook_context))

    def _target_refs_in_radius(
        self,
        hook_context: HookContext,
        summon: CreatedObjectRuntimeState,
    ) -> tuple[str, ...]:
        simulation = hook_context.simulation
        if simulation is None or simulation.space_runtime is None:
            return ()
        entities = simulation.space_runtime.entities_in_radius(
            summon.entity.position,
            self._radius,
            kinds={SpatialEntityKind.TARGET},
        )
        return tuple(entity.entity_id for entity in entities)

    def _targets(self, hook_context: HookContext) -> tuple[TargetRuntimeState, ...]:
        simulation = hook_context.simulation
        if simulation is None or simulation.space_runtime is None:
            return ()
        return simulation.space_runtime.targets.targets


class OdetteC4CoordinatedAttackHook:
    """C4 协同攻击：队伍角色造成星烁反应伤害命中敌人时，延迟 5 帧追加一次星变体伤害。

    触发按**任意角色**的星烁伤害事实（不按来源自筛，与桑多涅 C4 相反）；变体按
    落地帧的辉映证据分派（无辉映证据时走星超导变体）。触发帧写入内置冷却游标，
    排队帧与目标记在实例字段（短生命周期）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        slot: int,
        channel: OdetteStellarChannel,
        cooldown_frames: int,
        delay_frames: int = ODETTE_C4_COORDINATED_DELAY_FRAMES,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C4 协同攻击 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("C4 协同攻击必须绑定正整数队伍槽位")
        if cooldown_frames <= 0:
            raise ContentUnitValidationError("C4 协同攻击内置冷却必须为正帧数")
        if delay_frames < 0:
            raise ContentUnitValidationError("C4 协同攻击延迟不能为负数")
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._slot = slot
        self._channel = channel
        self._cooldown_frames = cooldown_frames
        self._delay_frames = delay_frames
        self._last_proc_frame: int | None = None
        self._pending: tuple[int, str] | None = None
        self.hook_key = f"odette.c4:{owner_ref}"
        self.state_key = ODETTE_CHARACTER_HANDLER_KEY
        self.subscriptions = ("DAMAGE_RESOLVED", "FRAME_STARTED")
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次排队协同攻击的触发帧；仅供测试读取。"""

        return self._last_proc_frame

    @property
    def cooldown_frames(self) -> int:
        """协同攻击内置冷却帧数；仅供测试与诊断读取。"""

        return self._cooldown_frames

    @property
    def delay_frames(self) -> int:
        """触发到落地的延迟帧数；仅供测试与诊断读取。"""

        return self._delay_frames

    def handle(self, event: object, context: object) -> HookResult:
        event_type = getattr(event, "event_type", None)
        frame = getattr(event, "frame", 0)
        if event_type is EventType.FRAME_STARTED:
            return self._release_pending(context, frame)
        if event_type is not EventType.DAMAGE_RESOLVED:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        source_ref = getattr(result, "source_ref", None)
        if not isinstance(source_ref, AttributeSubjectRef):
            return HookResult()
        if source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return HookResult()
        trigger_tag = getattr(result, "main_attack_tag", None)
        if not isinstance(trigger_tag, str) or trigger_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return HookResult()
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        if not isinstance(target_id, str) or not target_id.startswith(_ENEMY_TARGET_PREFIX):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            self._cooldown_frames
        ):
            return HookResult()
        self._last_proc_frame = frame
        self._pending = (frame + self._delay_frames, target_id)
        return HookResult()

    def _release_pending(self, context: object, frame: int) -> HookResult:
        pending = self._pending
        if pending is None or frame < pending[0]:
            return HookResult()
        self._pending = None
        hook_context = cast(HookContext, context)
        spec = resolve_stellar_variant_spec(
            self._channel,
            simulation=hook_context.simulation,
            owner_ref=self._owner_ref,
            frame=frame,
            conduct_fallback=True,
        )
        if spec is None:
            return HookResult()
        request_id = f"hook:{self.hook_key}:{frame}"
        return HookResult(
            impact_requests=(
                ImpactRequest(
                    frame=frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=ODETTE_C4_COORDINATED_IMPACT_KEY,
                    owner_slot=self._slot,
                    request_id=request_id,
                    target_refs=(pending[1],),
                    damage_spec=replace(
                        spec,
                        impact_ref=f"{request_id}:damage",
                    ),
                ),
            ),
        )


def compile_coordinated_attack_channel(
    *,
    conduct_ratio: float,
    swirl_ratio: float,
) -> OdetteStellarChannel:
    """按 C4 行的两档倍率编译协同攻击的星烁通道（单体，无 AOE、无附着）。"""

    if conduct_ratio <= 0.0 or swirl_ratio <= 0.0:
        raise ContentUnitValidationError("C4 协同攻击倍率必须为正数")
    return OdetteStellarChannel(
        impact_key=ODETTE_C4_COORDINATED_IMPACT_KEY,
        conduct_spec=stellar_variant_hit(
            impact_ref=ODETTE_C4_COORDINATED_IMPACT_KEY,
            main_attack_tag=STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
            display_name=ODETTE_C4_COORDINATED_DISPLAY_NAME,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=None,
        ),
        swirl_spec=stellar_variant_hit(
            impact_ref=ODETTE_C4_COORDINATED_IMPACT_KEY,
            main_attack_tag=STELLAR_SWIRL_ICE_DAMAGE_TAG,
            display_name=ODETTE_C4_COORDINATED_DISPLAY_NAME,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            area=None,
        ),
        conduct_ratio=conduct_ratio,
        swirl_ratio=swirl_ratio,
    )
