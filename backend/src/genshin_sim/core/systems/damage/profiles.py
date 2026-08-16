"""Damage Profile 到完整公式的稳定映射。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.systems.damage.models import DamageProfile


class DamageProfileRegistry:
    """按 profile key 和主攻击标签索引 DamageProfile。"""

    def __init__(self, profiles: Iterable[DamageProfile] = ()) -> None:
        self._profiles: dict[str, DamageProfile] = {}
        self._profiles_by_main_tag: dict[str, DamageProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: DamageProfile) -> None:
        if profile.profile_key in self._profiles:
            raise ValueError(f"重复的 DamageProfile：{profile.profile_key}")
        for tag in profile.main_attack_tags:
            if tag in self._profiles_by_main_tag:
                raise ValueError(f"主攻击标签重复映射 DamageProfile：{tag}")
        self._profiles[profile.profile_key] = profile
        for tag in profile.main_attack_tags:
            self._profiles_by_main_tag[tag] = profile

    def require(self, profile_key: str) -> DamageProfile:
        try:
            return self._profiles[profile_key]
        except KeyError as exc:
            raise KeyError(f"未注册的 DamageProfile：{profile_key}") from exc

    def require_for_main_attack_tag(self, main_attack_tag: str) -> DamageProfile:
        try:
            return self._profiles_by_main_tag[main_attack_tag]
        except KeyError as exc:
            raise KeyError(f"主攻击标签未映射 DamageProfile：{main_attack_tag}") from exc

    @property
    def profiles(self) -> tuple[DamageProfile, ...]:
        return tuple(sorted(self._profiles.values(), key=lambda item: item.profile_key))
