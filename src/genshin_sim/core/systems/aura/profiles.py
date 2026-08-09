"""已确认的标准 Aura 强度、附着损耗和衰减速率。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.systems.aura.enums import (
    AuraDecayProfilePolicy,
    AuraLossPolicy,
    AuraStrength,
)

FRAMES_PER_SECOND = 60


@dataclass(frozen=True, slots=True)
class AuraDecayProfile:
    strength: AuraStrength | None
    raw_amount: AuraAmount
    attached_amount: AuraAmount
    decay_per_second: AuraAmount

    def __post_init__(self) -> None:
        if self.strength is not None and not isinstance(self.strength, AuraStrength):
            raise ValueError("strength 必须是 AuraStrength 或 None")
        if self.raw_amount.is_zero:
            raise ValueError("raw_amount 必须为正数")
        if self.attached_amount.is_zero:
            raise ValueError("attached_amount 必须为正数")
        if self.decay_per_second.is_zero:
            raise ValueError("decay_per_second 必须为正数")

    def decay_for_frames(self, frames: int) -> AuraAmount:
        if frames < 0:
            raise ValueError("frames 不能为负数")
        return self.decay_per_second * Fraction(frames, FRAMES_PER_SECOND)


@dataclass(frozen=True, slots=True)
class AuraApplicationProfile:
    """正元素量施加使用的损耗和衰减档案解析规则。"""

    profile_key: str
    decay_profile_policy: AuraDecayProfilePolicy
    loss_policy: AuraLossPolicy = AuraLossPolicy.STANDARD_20_PERCENT

    def __post_init__(self) -> None:
        if not isinstance(self.profile_key, str) or not self.profile_key.strip():
            raise ValueError("profile_key 必须是非空字符串")
        if not isinstance(self.decay_profile_policy, AuraDecayProfilePolicy):
            raise ValueError("decay_profile_policy 必须是 AuraDecayProfilePolicy")
        if not isinstance(self.loss_policy, AuraLossPolicy):
            raise ValueError("loss_policy 必须是 AuraLossPolicy")
        if (
            self.decay_profile_policy is AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT
            and self.loss_policy is not AuraLossPolicy.STANDARD_20_PERCENT
        ):
            raise ValueError("常规附着公式只支持 STANDARD_20_PERCENT 损耗")

    def resolve_decay_profile(
        self,
        *,
        base_strength: AuraStrength,
        effective_raw_amount: AuraAmount | None,
    ) -> AuraDecayProfile:
        if self.decay_profile_policy is AuraDecayProfilePolicy.STANDARD_STRENGTH:
            return profile_for(base_strength)
        if self.decay_profile_policy is AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT:
            if effective_raw_amount is None:
                raise ValueError("常规附着公式必须提供 effective_raw_amount")
            return regular_application_decay_profile(effective_raw_amount)
        raise ValueError(f"不支持的 Aura 衰减档案策略：{self.decay_profile_policy!r}")


class AuraApplicationProfileRegistry:
    """派生元素施加只能引用已显式注册的应用 Profile。"""

    def __init__(self, profiles: tuple[AuraApplicationProfile, ...] = ()) -> None:
        self._profiles: dict[str, AuraApplicationProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: AuraApplicationProfile) -> None:
        if profile.profile_key in self._profiles:
            raise ValueError(f"重复的 Aura application profile：{profile.profile_key}")
        self._profiles[profile.profile_key] = profile

    def require(self, profile_key: str) -> AuraApplicationProfile:
        if not isinstance(profile_key, str) or not profile_key.strip():
            raise ValueError("profile_key 必须是非空字符串")
        try:
            return self._profiles[profile_key]
        except KeyError as exc:
            raise ValueError(f"缺少 Aura application profile：{profile_key}") from exc


def regular_application_duration(raw_amount: AuraAmount) -> Fraction:
    """常规附着的自然持续时间，单位为秒。"""

    if raw_amount.is_zero:
        raise ValueError("raw_amount 必须为正数")
    return Fraction(7) + Fraction(5, 2) * raw_amount.value


def regular_application_decay_profile(
    raw_amount: AuraAmount,
    *,
    strength: AuraStrength | None = None,
) -> AuraDecayProfile:
    """按常规附着公式构造精确的线性衰减档案。"""

    attached = raw_amount * Fraction(4, 5)
    return AuraDecayProfile(
        strength=strength,
        raw_amount=raw_amount,
        attached_amount=attached,
        decay_per_second=attached / regular_application_duration(raw_amount),
    )


STANDARD_AURA_PROFILES: dict[AuraStrength, AuraDecayProfile] = {
    AuraStrength.WEAK: regular_application_decay_profile(AuraAmount(1), strength=AuraStrength.WEAK),
    AuraStrength.MEDIUM: regular_application_decay_profile(
        AuraAmount(Fraction(3, 2)), strength=AuraStrength.MEDIUM
    ),
    AuraStrength.STRONG: regular_application_decay_profile(
        AuraAmount(2), strength=AuraStrength.STRONG
    ),
    AuraStrength.SUPER_STRONG: regular_application_decay_profile(
        AuraAmount(4), strength=AuraStrength.SUPER_STRONG
    ),
}


def profile_for(strength: AuraStrength) -> AuraDecayProfile:
    try:
        return STANDARD_AURA_PROFILES[strength]
    except KeyError as exc:
        raise ValueError(f"不支持的 AuraStrength：{strength!r}") from exc


def quicken_decay_profile(amount: AuraAmount) -> AuraDecayProfile:
    (
        """精确激元素衰减档案。

    设新激元素量为 ``Q`` GU：

    duration_seconds = 6 + 5 * Q
    duration_frames  = 60 * (6 + 5 * Q)
    decay_per_frame  = Q / (360 + 300 * Q)

    激元素不应用普通附着损耗；当前量、衰减率与持续时间均使用精确有理数保存。
    """
        ""
    )

    if amount.is_zero:
        raise ValueError("激元素量必须为正数")
    duration_seconds = Fraction(6) + Fraction(5) * amount.value
    decay_per_second_value = amount.value / duration_seconds
    return AuraDecayProfile(
        strength=None,
        raw_amount=amount,
        attached_amount=amount,
        decay_per_second=AuraAmount(decay_per_second_value),
    )


def attached_amount(
    strength: AuraStrength,
    coefficient: AuraAmount,
    loss_policy: AuraLossPolicy,
    effective_raw_amount: AuraAmount | None = None,
) -> AuraAmount:
    profile = profile_for(strength)
    raw_amount = effective_raw_amount or profile.raw_amount * coefficient
    if loss_policy is AuraLossPolicy.STANDARD_20_PERCENT:
        return raw_amount * Fraction(4, 5)
    if loss_policy is AuraLossPolicy.LOSSLESS:
        return raw_amount
    raise ValueError(f"不支持的 Aura 损耗策略：{loss_policy!r}")
