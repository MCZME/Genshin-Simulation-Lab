from __future__ import annotations

import logging


def flush_project_handlers() -> None:
    """冲刷 genshin_sim 根 logger 的全部 handler（测试收尾工具）。"""

    for handler in logging.getLogger("genshin_sim").handlers:
        handler.flush()
