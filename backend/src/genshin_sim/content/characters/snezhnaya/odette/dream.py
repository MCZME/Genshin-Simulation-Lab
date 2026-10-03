"""奥黛塔雪鹄之梦体系（元素爆发）与 C4 均摊。

机制口径（资产技能文本，规划文档切片 6）：

- **雪鹄之梦**（`雪鹄变奏` 技能文本「获得雪鹄之梦：提升奥黛塔造成的星烁反应
  伤害」）：施放元素爆发后获得的自身标记 Buff，持续 20 秒（重施放刷新）。提升
  值随 Q 等级成长（资产倍率表条目「雪鹄之梦星烁反应伤害提升」，Lv1 0.14），
  持续秒数取「雪鹄之梦持续时间」（20 秒）。
- **C4 均摊**（「奥黛塔获得雪鹄之梦时，还会使队伍中附近的其他角色造成的星烁
  反应伤害提升，提升值相当于雪鹄之梦效果的 50%」）：持有雪鹄之梦期间，**其他
  队伍角色**造成的星烁反应伤害按其 50% 提升（比例取 C4 行 number_1）。

数值在内容编译期按有效 Q 等级（含 C5 的 +3）编译为确定值；运行期只判定标记
存在性（`TargetBuffPresenceReadPort`），增伤经 ``stellar_reaction_bonus_add``
词条在结算期进入星烁公式（D-082：不预乘进星烁输入基线）。标记 Buff 本身是
纯载体（``marker_only``），不带属性词条。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_SWAN_DREAM_BONUS_TALENT_LABEL,
    ODETTE_SWAN_DREAM_BUFF_MECHANIC_KEY,
    ODETTE_SWAN_DREAM_DURATION_TALENT_LABEL,
    ODETTE_SWAN_DREAM_GRANT_IMPACT_KEY,
    odette_swan_dream_definition_key,
)
from genshin_sim.content.characters.snezhnaya.odette.stellar import (
    STELLAR_REACTION_DAMAGE_TAGS,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffDefinition,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

FRAMES_PER_SECOND = 60


class OdetteSwanDreamError(RuntimeError):
    """雪鹄之梦体系运行期错误（接线缺失或契约不完整）。"""


@dataclass(frozen=True, slots=True)
class SwanDreamValues:
    """雪鹄之梦的编译期取值（唯一来源是资产倍率表，随有效 Q 等级确定）。"""

    stellar_bonus: float
    duration_frames: int

    def __post_init__(self) -> None:
        if not 0.0 < self.stellar_bonus <= 1.0:
            raise ContentUnitValidationError("雪鹄之梦星烁反应伤害提升必须在 (0, 1] 区间")
        if self.duration_frames <= 0:
            raise ContentUnitValidationError("雪鹄之梦持续时间必须是正帧数")


@dataclass(frozen=True, slots=True)
class SwanDreamGrantConfig:
    """雪鹄之梦发放参数（内容编译期冻结，随角色单元交给影响工厂）。"""

    definition_key: str
    duration_frames: int


def read_swan_dream_values(
    character_key: str,
    entries_by_key: Mapping[tuple[str, str, str], TalentScalingEntry],
    burst_talent_level: int,
) -> SwanDreamValues:
    """从元素爆发表读取雪鹄之梦的星烁增伤与持续帧数（按有效 Q 等级编译）。"""

    bonus_entry = entries_by_key.get(
        (character_key, "elemental_burst", ODETTE_SWAN_DREAM_BONUS_TALENT_LABEL)
    )
    if bonus_entry is None:
        raise ContentUnitValidationError(
            f"奥黛塔元素爆发缺少资产倍率条目：{ODETTE_SWAN_DREAM_BONUS_TALENT_LABEL}"
        )
    duration_entry = entries_by_key.get(
        (character_key, "elemental_burst", ODETTE_SWAN_DREAM_DURATION_TALENT_LABEL)
    )
    if duration_entry is None:
        raise ContentUnitValidationError(
            f"奥黛塔元素爆发缺少资产倍率条目：{ODETTE_SWAN_DREAM_DURATION_TALENT_LABEL}"
        )
    bonus = ScalingCompiler.compile_entry(bonus_entry, burst_talent_level)
    duration = ScalingCompiler.compile_entry(duration_entry, burst_talent_level)
    if not bonus.components or not duration.components:
        raise ContentUnitValidationError("雪鹄之梦倍率条目缺少数值分量")
    seconds = duration.components[0].value
    if seconds <= 0.0:
        raise ContentUnitValidationError("雪鹄之梦持续秒数必须为正数")
    return SwanDreamValues(
        stellar_bonus=bonus.components[0].value,
        duration_frames=round(seconds * FRAMES_PER_SECOND),
    )


def build_swan_dream_buff_definition(
    slot: int,
    *,
    handler_key: str,
    display_name: str,
) -> BuffDefinition:
    """编译雪鹄之梦 Buff 定义：自身标记载体，单层、重施放刷新期限。"""

    definition_key = odette_swan_dream_definition_key(slot)
    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=ODETTE_SWAN_DREAM_BUFF_MECHANIC_KEY,
        handler_key=handler_key,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        display_name=display_name,
    )


def swan_dream_grant_request(
    *,
    frame: int,
    slot: int,
    definition_key: str,
    duration_frames: int,
) -> ImpactRequest:
    """构造雪鹄之梦发放请求（目标固定为奥黛塔本人）。"""

    owner_ref = f"character:slot_{slot}"
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_STATUS,
        impact_key=ODETTE_SWAN_DREAM_GRANT_IMPACT_KEY,
        owner_slot=slot,
        request_id=f"odette.swan_dream:{frame}:grant",
        target_refs=(owner_ref,),
        params={
            "buff": {
                "definition_key": definition_key,
                "duration_frames": duration_frames,
                "stack_delta": 1,
                "applier_ref": AttributeSubjectRef.character(owner_ref).to_dict(),
            },
        },
    )


class OdetteSwanDreamStellarBonusProvider:
    """雪鹄之梦：持有期间奥黛塔自身造成的星烁反应伤害提升（词条通道）。

    数值随有效 Q 等级在编译期确定；运行期只判定标记是否存在（持有层数 ≥ 1）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        definition_key: str,
        stellar_bonus: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("雪鹄之梦 owner_ref 必须是非空字符串")
        if not 0.0 < stellar_bonus <= 1.0:
            raise ContentUnitValidationError("雪鹄之梦星烁增伤必须在 (0, 1] 区间")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._definition_key = definition_key
        self._stellar_bonus = stellar_bonus
        self._provider_key = f"{source_key}.swan_dream:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配期注入目标 Buff 只读端口；未绑定时 provider 不产出词条。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        if self._target_status_port is None:
            return ()
        request = query.request
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.source_ref != self._owner_ref:
            return ()
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        if not self._holds_swan_dream(request.frame):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._stellar_bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )

    def _holds_swan_dream(self, frame: int) -> bool:
        assert self._target_status_port is not None
        return (
            self._target_status_port.active_stack_count(
                target_ref=self._owner_ref,
                definition_key=self._definition_key,
                frame=frame,
            )
            >= 1
        )


class OdetteC4SwanDreamShareProvider:
    """C4 均摊：持有雪鹄之梦期间，其他队伍角色的星烁反应伤害提升其 ``share_ratio``。

    按伤害来源自筛为**其他角色**（文本「队伍中附近的其他角色」；奥黛塔自己走
    雪鹄之梦本体 provider，不重复计入）。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        definition_key: str,
        share_bonus: float,
        source_key: str,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("C4 均摊 owner_ref 必须是非空字符串")
        if not 0.0 < share_bonus <= 1.0:
            raise ContentUnitValidationError("C4 均摊提升值必须在 (0, 1] 区间")
        self._owner_ref = AttributeSubjectRef.character(owner_ref)
        self._definition_key = definition_key
        self._share_bonus = share_bonus
        self._provider_key = f"{source_key}.swan_dream_share:{owner_ref}"
        self._source_ref = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._target_status_port: TargetBuffPresenceReadPort | None = None
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.STELLAR_REACTION_BONUS_ADD}),
            owner_ref=self._owner_ref,
            display_name=display_name,
        )

    def bind_runtime_ports(self, *, target_status_port: TargetBuffPresenceReadPort) -> None:
        """装配期注入目标 Buff 只读端口；未绑定时 provider 不产出词条。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        if self._target_status_port is None:
            return ()
        request = query.request
        if request.formula_key != FORMULA_KEY_STELLAR_REACTION:
            return ()
        if request.source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return ()
        if request.source_ref == self._owner_ref:
            return ()
        if request.main_attack_tag not in STELLAR_REACTION_DAMAGE_TAGS:
            return ()
        if (
            self._target_status_port.active_stack_count(
                target_ref=self._owner_ref,
                definition_key=self._definition_key,
                frame=request.frame,
            )
            < 1
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.STELLAR_REACTION_BONUS_ADD,
                value=self._share_bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
            ),
        )
