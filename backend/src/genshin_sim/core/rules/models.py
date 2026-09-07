"""规则系统的中立模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuleActivation:
    """一条被激活的规则与其原始参数。"""

    rule_key: str
    params: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RuleResolutionContext:
    """规则解析时可读取的仿真级输入。"""

    seed: int
