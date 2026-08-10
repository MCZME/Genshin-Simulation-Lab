"""月兆快照模型。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.systems.moonsign.errors import MoonsignValidationError


@dataclass(frozen=True, slots=True)
class MoonsignSnapshot:
    """指定帧的月兆等级与当前月曜增伤概要。"""

    frame: int
    level: str
    moonsign_character_refs: tuple[str, ...]
    bonus: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise MoonsignValidationError("快照帧必须是非负整数")
        if not isinstance(self.level, str) or not self.level:
            raise MoonsignValidationError("level 必须是非空字符串")
        refs = tuple(self.moonsign_character_refs)
        if refs != tuple(sorted(set(refs))):
            raise MoonsignValidationError("月兆角色引用必须排序去重")
        object.__setattr__(self, "moonsign_character_refs", refs)

    def to_dict(self) -> dict[str, object]:
        return {
            "frame": self.frame,
            "level": self.level,
            "moonsign_character_refs": tuple(self.moonsign_character_refs),
            "bonus": self.bonus,
        }
