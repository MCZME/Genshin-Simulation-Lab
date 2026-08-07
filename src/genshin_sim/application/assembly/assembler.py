"""仿真组装门面：配置转化 -> 数据查询 -> 内容编译 -> 运行时装配。"""

from __future__ import annotations

from genshin_sim.application.assembly.models import (
    AssembledSimulation,
)
from genshin_sim.application.assembly.stages import (
    AssetBundleLoader,
    ConfigTranslator,
    ContentCompiler,
    RuntimeAssembler,
)
from genshin_sim.application.config import SimulationConfig
from genshin_sim.assets import AssetRepository
from genshin_sim.content.bootstrap_content_units import (
    create_default_content_unit_registry,
)
from genshin_sim.content.registries import ContentUnitRegistry
from genshin_sim.core.systems.damage import DamageFormulaRegistry


class SimulationAssembler:
    """构建阶段门面：组合四个独立阶段产出可运行世界。"""

    def __init__(
        self,
        asset_repository: AssetRepository,
        *,
        damage_formula_registry: DamageFormulaRegistry | None = None,
        content_unit_registry: ContentUnitRegistry | None = None,
    ) -> None:
        self.asset_repository = asset_repository
        self.damage_formula_registry = damage_formula_registry
        if content_unit_registry is None:
            content_unit_registry = create_default_content_unit_registry()
        self.config_translator = ConfigTranslator()
        self.asset_loader = AssetBundleLoader(asset_repository)
        self.content_compiler = ContentCompiler(
            content_unit_registry=content_unit_registry,
        )
        self.runtime_assembler = RuntimeAssembler(
            damage_formula_registry=damage_formula_registry,
        )

    def assemble(self, config: SimulationConfig) -> AssembledSimulation:
        config = self.config_translator.translate(config)
        assets = self.asset_loader.load(config)
        content_bundle = self.content_compiler.compile(config, assets)
        return self.runtime_assembler.assemble(config, assets, content_bundle)
