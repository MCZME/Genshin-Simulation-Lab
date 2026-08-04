"""元素领域共享的稳定身份。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


class ElementalSubjectKind(StrEnum):
    CHARACTER = "character"
    TARGET = "target"
    CREATED_OBJECT = "created_object"


class TransformativeReactionSourceKind(StrEnum):
    """剧变反应等级系数使用的中立来源分类。"""

    CHARACTER = "character"
    ENEMY_ENVIRONMENT = "enemy_environment"


@dataclass(frozen=True, order=True, slots=True)
class ElementalSubjectRef:
    kind: ElementalSubjectKind
    entity_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ElementalSubjectKind):
            raise ValueError("不支持的元素交互主体类型")
        _text(self.entity_id, "entity_id")

    @classmethod
    def character(cls, entity_id: str) -> ElementalSubjectRef:
        return cls(ElementalSubjectKind.CHARACTER, entity_id)

    @classmethod
    def target(cls, entity_id: str) -> ElementalSubjectRef:
        return cls(ElementalSubjectKind.TARGET, entity_id)

    @classmethod
    def created_object(cls, entity_id: str) -> ElementalSubjectRef:
        return cls(ElementalSubjectKind.CREATED_OBJECT, entity_id)


@dataclass(frozen=True, order=True, slots=True)
class ElementalSourceRef:
    """施加者与 Aura 贡献者共用的中立归属引用。"""

    source_key: str
    instance_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.source_key, "source_key")
        if self.instance_id is not None:
            _text(self.instance_id, "instance_id")

    def to_dict(self) -> dict[str, str | None]:
        return {"source_key": self.source_key, "instance_id": self.instance_id}


@dataclass(frozen=True, order=True, slots=True)
class ElementalStateLinkRef:
    """Aura Component 与未来 Reaction 状态之间的中立关联。"""

    link_key: str

    def __post_init__(self) -> None:
        _text(self.link_key, "link_key")
