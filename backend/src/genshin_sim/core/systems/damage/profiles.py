"""主攻击标签到完整公式的稳定映射与默认兜底。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.systems.damage.errors import UnsupportedDamageFormulaError
from genshin_sim.core.systems.damage.keys import (
    DEFAULT_FORMULA_KEY,
    REACTION_TAG_PREFIX,
)
from genshin_sim.core.systems.damage.models import DamageProfile

_DEFAULT_GENERAL_PROFILE = DamageProfile(DEFAULT_FORMULA_KEY, frozenset())


class DamageProfileRegistry:
    """按主攻击标签解析 DamageProfile 映射。

    显式注册只覆盖非通用公式（剧变、月曜等）；未注册的非反应命名空间标签
    默认使用通用公式，``reaction.`` 前缀标签未注册时明确报错，防止反应
    标签笔误静默降级为通用伤害。
    """

    def __init__(self, profiles: Iterable[DamageProfile] = ()) -> None:
        self._profiles_by_tag: dict[str, DamageProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: DamageProfile) -> None:
        if not isinstance(profile, DamageProfile):
            raise ValueError("DamageProfileRegistry 只能注册 DamageProfile")
        if not profile.main_attack_tags:
            raise ValueError("显式注册的 DamageProfile 至少需要一个主攻击标签")
        for tag in profile.main_attack_tags:
            if tag in self._profiles_by_tag:
                raise ValueError(f"主攻击标签重复映射 DamageProfile：{tag}")
            self._profiles_by_tag[tag] = profile

    def resolve_for_main_attack_tag(self, main_attack_tag: str) -> DamageProfile:
        """返回标签对应的映射；未注册标签按命名空间决定默认或报错。"""

        try:
            return self._profiles_by_tag[main_attack_tag]
        except KeyError as exc:
            if main_attack_tag.startswith(REACTION_TAG_PREFIX):
                raise UnsupportedDamageFormulaError(
                    f"反应标签未映射 DamageProfile：{main_attack_tag}"
                ) from exc
            return _DEFAULT_GENERAL_PROFILE

    @property
    def profiles(self) -> tuple[DamageProfile, ...]:
        """按主攻击标签稳定排序返回全部显式注册条目。"""

        return tuple(
            sorted(
                self._profiles_by_tag.values(),
                key=lambda item: sorted(item.main_attack_tags)[0],
            )
        )
