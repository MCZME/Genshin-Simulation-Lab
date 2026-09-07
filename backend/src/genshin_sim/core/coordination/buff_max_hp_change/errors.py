from __future__ import annotations


class BuffMaxHpChangeError(Exception):
    """Buff 最大生命同步协调错误基类。"""


class BuffMaxHpChangeCommitError(BuffMaxHpChangeError):
    """预校验后的领域提交违反不得失败契约。"""


class BuffMaxHpChangeReentrancyError(BuffMaxHpChangeError):
    """事件回调同步重入协调器。"""
