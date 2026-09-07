"""元素共鸣测试共享的假只读端口与伤害查询构造器。"""

from __future__ import annotations

from types import SimpleNamespace

from genshin_sim.core.attributes import (
    AttributeSubjectKind,
    AttributeSubjectRef,
)


class FakeAuraFrozenPort:
    """可配置的目标冰附着/冻结只读端口。"""

    def __init__(self, result: bool) -> None:
        self.result = result

    def has_cryo_or_frozen(
        self,
        target_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool:
        del target_ref, frame
        return self.result


class FakeShieldPresencePort:
    """可配置的角色护盾庇护只读端口。"""

    def __init__(self, result: bool) -> None:
        self.result = result

    def has_active_shield(
        self,
        character_ref: AttributeSubjectRef,
        frame: int,
    ) -> bool:
        del character_ref, frame
        return self.result


class FakeLunarCagePresencePort:
    """可配置的月笼存在只读端口。"""

    def __init__(self, result: bool) -> None:
        self.result = result

    def has_active_lunar_cage(self) -> bool:
        return self.result


def make_damage_modifier_query(
    *,
    source_kind: AttributeSubjectKind = AttributeSubjectKind.CHARACTER,
    target_kind: AttributeSubjectKind = AttributeSubjectKind.TARGET,
    frame: int = 70,
) -> SimpleNamespace:
    """构造伤害修饰 provider 查询替身。"""

    source_ref = (
        AttributeSubjectRef(source_kind, "character:slot_1")
        if source_kind is AttributeSubjectKind.CHARACTER
        else AttributeSubjectRef(source_kind, "target:1")
    )
    target_ref = (
        AttributeSubjectRef(target_kind, "target:1")
        if target_kind is AttributeSubjectKind.TARGET
        else AttributeSubjectRef(target_kind, "character:slot_1")
    )
    return SimpleNamespace(
        request=SimpleNamespace(
            source_ref=source_ref,
            target_ref=target_ref,
            frame=frame,
        )
    )
