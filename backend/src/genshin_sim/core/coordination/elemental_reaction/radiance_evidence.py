"""星烁辉映证据的只读适配器（Buff 载荷词条 → 领域窄端口）。

该模块是辉映 Buff 载荷词条的读取侧窄入口：只组合 Buff 读取端口上的活动
记录载荷，不推进时间、不修改状态、不发布事实。变体优先级（同一角色同时
满足两种辉映条件时星超导生效，D-017 口径）在此执行，内容端不接触 Buff
definition key 与词条细节。
"""

from __future__ import annotations

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
    STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
)
from genshin_sim.core.systems.buff import BuffReader
from genshin_sim.core.systems.reaction.radiance import (
    RadianceEvidence,
    RadianceVariant,
)

_VARIANT_TERM_KEYS: dict[RadianceVariant, tuple[str, str]] = {
    RadianceVariant.CONDUCT: (
        STELLAR_RADIANCE_BUFF_DEFINITION_KEY,
        STELLAR_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
    ),
    RadianceVariant.SWIRL: (
        STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
        STELLAR_SWIRL_RADIANCE_DIRECT_MULTIPLIER_TERM_KEY,
    ),
}


class StellarRadianceEvidenceReader:
    """包装 ``BuffReader`` 的辉映证据读取端口实现（纯只读）。"""

    def __init__(self, reader: BuffReader) -> None:
        self._reader = reader

    def resolve(self, *, owner_ref: str, frame: int) -> RadianceEvidence | None:
        conduct = self.variant_multiplier(
            owner_ref=owner_ref, variant=RadianceVariant.CONDUCT, frame=frame
        )
        if conduct > 0.0:
            return RadianceEvidence(RadianceVariant.CONDUCT, conduct)
        swirl = self.variant_multiplier(
            owner_ref=owner_ref, variant=RadianceVariant.SWIRL, frame=frame
        )
        if swirl > 0.0:
            return RadianceEvidence(RadianceVariant.SWIRL, swirl)
        return None

    def variant_multiplier(self, *, owner_ref: str, variant: RadianceVariant, frame: int) -> float:
        definition_key, term_key = _VARIANT_TERM_KEYS[variant]
        records = self._reader.active(
            frame,
            target_ref=AttributeSubjectRef.character(owner_ref),
            definition_key=definition_key,
        )
        for record in records:
            for payload in record.state.resolved_payloads:
                if payload.term_key == term_key:
                    return payload.value
        return 0.0
