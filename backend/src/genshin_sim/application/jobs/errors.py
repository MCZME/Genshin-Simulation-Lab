"""仿真任务错误。"""


class SimulationJobError(Exception):
    """仿真任务的基础错误。"""


class SimulationJobNotFoundError(SimulationJobError, LookupError):
    """指定仿真任务不存在。"""


class SimulationJobPayloadError(SimulationJobError, ValueError):
    """仿真任务 payload 不合法。"""
