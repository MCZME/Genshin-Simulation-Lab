"""元素能量系统的装配期策略协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class InitialEnergyPolicy(Protocol):
    """开局元素能量策略：由角色能量上限推导初始能量。"""

    def initial_energy(self, capacity: float) -> float:
        """返回开局时的当前元素能量。"""
        ...


class ZeroInitialEnergyPolicy:
    """默认策略：开局元素能量为 0。"""

    def initial_energy(self, capacity: float) -> float:
        del capacity
        return 0.0


class FullInitialEnergyPolicy:
    """满能量开局策略：开局元素能量等于上限。"""

    def initial_energy(self, capacity: float) -> float:
        return capacity
