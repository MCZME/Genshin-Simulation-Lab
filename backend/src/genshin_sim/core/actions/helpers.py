"""动作模块内部校验与参数辅助。"""

from __future__ import annotations


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} 必须是非空字符串"
        raise ValueError(msg)
