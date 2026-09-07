"""元素共鸣反应触发的跨系统响应协调器。

消费已提交的反应与伤害事实，为下一结算轮次生成能量、Buff 等强类型意图；
不直接写入其他领域状态。
"""

from genshin_sim.core.coordination.resonance_reaction.stage import ResonanceReactionStage

__all__ = ["ResonanceReactionStage"]
