"""server 单元测试共享脚手架。"""

from collections.abc import Callable
from typing import cast

import pytest

from genshin_sim.application import ApplicationFacade, WorkspaceInfo

ApplicationFacadeFactory = Callable[[WorkspaceInfo], ApplicationFacade]


@pytest.fixture
def application_facade() -> ApplicationFacadeFactory:
    """构造只暴露 workspace 能力的 server facade 替身。"""

    def make(workspace: WorkspaceInfo) -> ApplicationFacade:
        class _FakeFacade:
            def get_workspace(self) -> WorkspaceInfo:
                return workspace

        return cast(ApplicationFacade, _FakeFacade())

    return make
