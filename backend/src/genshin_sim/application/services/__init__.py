"""UI 与 CLI 共享的用例服务。"""

from genshin_sim.application.services.assets import (
    AssetDatabaseService,
    AssetHandlerBindingService,
    AssetListItem,
    AssetListKind,
    AssetManifestAuditService,
    AssetManifestBuildService,
    AssetSourceCacheService,
    AssetsService,
    HandlerBindingKind,
)
from genshin_sim.application.services.errors import ApplicationServiceError
from genshin_sim.application.services.input_validation import InputValidationService
from genshin_sim.application.services.inputs import InputDiscoveryService
from genshin_sim.application.services.models import (
    RunDetail,
    RunListItem,
)
from genshin_sim.application.services.project import ProjectService
from genshin_sim.application.services.protocols import (
    ResultRepository,
    SimulationInputValidator,
)
from genshin_sim.application.services.results import ResultDatabaseService, ResultsService
from genshin_sim.application.services.simulation import SimulationTaskService

__all__ = [
    "ApplicationServiceError",
    "AssetDatabaseService",
    "AssetHandlerBindingService",
    "AssetListItem",
    "AssetListKind",
    "AssetManifestAuditService",
    "AssetManifestBuildService",
    "AssetSourceCacheService",
    "AssetsService",
    "InputValidationService",
    "InputDiscoveryService",
    "ProjectService",
    "SimulationInputValidator",
    "HandlerBindingKind",
    "ResultRepository",
    "ResultDatabaseService",
    "ResultsService",
    "RunDetail",
    "RunListItem",
    "SimulationTaskService",
]
