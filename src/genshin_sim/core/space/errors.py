from __future__ import annotations


class SpaceEntityPlanConflictError(RuntimeError):
    """空间实体变更计划与当前投影或已提交操作冲突。"""
