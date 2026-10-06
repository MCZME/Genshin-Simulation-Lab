"""阿罗夏测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import EffectPayload, TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_FULGURITE_OBJECT_KEY,
    ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
    ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
    ALYOSHA_TEAM_SCOPE,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。
ALYOSHA_CHARACTER_KEY = "character:alyosha_test"
ALYOSHA_REF = AttributeSubjectRef.character("character:slot_1")


def alyosha_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
    targets: list[dict[str, object]] | None = None,
    constellation: int = 0,
    level: int = 90,
) -> dict[str, object]:
    """阿罗夏单人集成测试配置。"""

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": input_key, "phase": "press"}]},
            {"frame": 2, "events": [{"key": input_key, "phase": "release"}]},
        ]
    if targets is None:
        targets = [
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            }
        ]
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "alyosha integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": ALYOSHA_CHARACTER_KEY,
                    "level": level,
                    "constellation": constellation,
                    "talents": {
                        "normal_attack": 1,
                        "elemental_skill": 1,
                        "elemental_burst": 1,
                    },
                },
                "artifacts": {"sets": [], "stats": {}},
            }
        ],
        "scene": {"targets": targets},
        "input_trace": input_trace,
        "rules": {"active": []},
        "run_options": {"max_frames": max_frames},
    }


def alyosha_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def apply_aura(assembled, element: Element, *, entity_id: str = "target:target_1") -> None:
    """仿真前经元素结算协调器种入元素附着（供反应触发类用例）。"""

    from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
        ElementalSettlementCoordinator,
    )

    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    request_id = f"test:alyosha:aura:{element.value}"
    coordinator.settle_aura_impact(
        assembled.context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.APPLY_AURA,
            impact_key=f"test.alyosha.aura_application.{element.value}",
            owner_slot=1,
            request_id=request_id,
            target_refs=(entity_id,),
            elemental_application_spec=ElementalApplicationSpec(
                impact_ref=f"{request_id}:spec",
                element=element,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        ),
    )


def mark_records(assembled, *, frame: int, entity_id: str = "target:target_1") -> tuple:
    """读取目标身上的弋猎印记活动记录。"""

    buff_runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(buff_runtime, BuffRuntime)
    return buff_runtime.reader.active(
        frame,
        target_ref=AttributeSubjectRef.target(entity_id),
        definition_key=ALYOSHA_HUNTERS_MARK_BUFF_DEFINITION_KEY,
    )


def precision_records(assembled, *, frame: int) -> tuple:
    """读取前台主体（ACTIVE_CHARACTER）上的猎者之准活动记录。"""

    buff_runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(buff_runtime, BuffRuntime)
    return buff_runtime.reader.active(
        frame,
        target_ref=AttributeSubjectRef.active_character(ALYOSHA_TEAM_SCOPE),
        definition_key=ALYOSHA_HUNTERS_PRECISION_BUFF_DEFINITION_KEY,
    )


def mastery_records(assembled, *, frame: int) -> tuple:
    """读取前台主体上的 C6 叠满精通伴生 Buff 活动记录。"""

    buff_runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(buff_runtime, BuffRuntime)
    return buff_runtime.reader.active(
        frame,
        target_ref=AttributeSubjectRef.active_character(ALYOSHA_TEAM_SCOPE),
        definition_key=ALYOSHA_HUNTERS_PRECISION_MASTERY_BUFF_DEFINITION_KEY,
    )


def resolved_atk(assembled, *, frame: int = 1) -> float:
    """解析阿罗夏当前面板攻击力（供相对断言折算）。"""

    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref=ALYOSHA_REF,
            attribute_key=STAT_ATK_TOTAL,
            frame=frame,
        )
    )
    return float(resolution.final_value)


def fulgurite_objects(assembled) -> tuple:
    """返回轰霆猎场创建实体运行态（类型键过滤）。"""

    runtime = assembled.space_runtime.created_object_runtime
    return tuple(obj for obj in runtime.objects if obj.type_key == ALYOSHA_FULGURITE_OBJECT_KEY)


def current_energy(assembled, *, frame: int = 0) -> float:
    """读取阿罗夏当前元素能量。"""

    from genshin_sim.core.systems.energy import EnergyRuntime

    runtime = assembled.context.get_system(EnergyRuntime)
    assert isinstance(runtime, EnergyRuntime)
    return runtime.get_current_energy(ALYOSHA_REF)


def write_alyosha_asset_database(db_path: Path) -> Path:
    """写入阿罗夏单人最小合成资产库（倍率数值默认全部为 1.0）。"""

    from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats

    characters = (
        CharacterAsset(
            asset_key=ALYOSHA_CHARACTER_KEY,
            source_id=ALYOSHA_CHARACTER_KEY.removeprefix("character:"),
            name="阿罗夏",
            element="electro",
            weapon_type="polearm",
            rarity=4,
            burst_energy_cost=70.0,
            handler_key=ALYOSHA_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=ALYOSHA_CHARACTER_KEY,
            level=90,
            ascension_phase=6,
            base_hp=10_000.0,
            base_atk=200.0,
            base_def=600.0,
            ascension_stat="crit_rate",
            ascension_value=0.0,
        ),
    )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "alyosha-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-alyosha-minimal",
            "source_version": "1",
            "content_hash": "alyosha-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_alyosha_scaling_entries(),
        effect_payloads=minimal_alyosha_effect_payloads(),
    )


def minimal_alyosha_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回阿罗夏 content 工厂接线所需的最小倍率行。

    倍率条目全部取 1.0、定值条目取与资产行同构的合成定值（E/Q 冷却 15s/18s、
    印记与猎者之准持续 15s、Q 场域持续 14s），只保证结构（label、分量数与
    等级区间）满足工厂编译；三段伤害带两个分量对应 3A/3B 双判定。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",), None),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",), None),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio", "plain_ratio"), None),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",), None),
        ("na_charged", "normal_attack", "重击伤害", ("plain_ratio",), None),
        ("es_press", "elemental_skill", "点按伤害", ("plain_ratio",), None),
        ("es_hold", "elemental_skill", "长按伤害", ("plain_ratio",), None),
        ("es_cooldown", "elemental_skill", "冷却时间", ("plain_value",), 15.0),
        ("es_mark_duration", "elemental_skill", "弋猎印记持续时间", ("plain_value",), 15.0),
        (
            "es_precision_atk",
            "elemental_skill",
            "猎者之准攻击力提升",
            ("plain_ratio",),
            None,
        ),
        (
            "es_precision_duration",
            "elemental_skill",
            "猎者之准持续时间",
            ("plain_value",),
            15.0,
        ),
        ("eb_field", "elemental_burst", "轰霆猎场伤害", ("plain_ratio",), None),
        ("eb_tugarin", "elemental_burst", "图加林伤害", ("plain_ratio",), None),
        ("eb_duration", "elemental_burst", "持续时间", ("plain_value",), 14.0),
        ("eb_cooldown", "elemental_burst", "冷却时间", ("plain_value",), 18.0),
    )
    return tuple(
        TalentScalingEntry(
            character_key=ALYOSHA_CHARACTER_KEY,
            talent_key=talent_key,
            entry_key=entry_key,
            label=label,
            scaling={
                "schema_version": 1,
                "mode": "level_table",
                "level_min": 1,
                "level_max": 15,
                "components": tuple(
                    {
                        "source_param": f"param_{index}",
                        "kind": kind,
                        "values": tuple(fixed if fixed is not None else 1.0 for _ in range(15)),
                    }
                    for index, kind in enumerate(kinds)
                ),
            },
            tags=(talent_key,),
        )
        for entry_key, talent_key, label, kinds, fixed in specs
    )


def minimal_alyosha_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回被动/命座集成测试需要的合成效果行。

    分量布局与真实资产行同构（内部引用位置用占位数 999.0，机器数值取便于
    断言的合成值）：C3/C5 携带天赋提升、P4/C4 携带回血比例、P5 携带充能
    效率折算三元组、P6 携带每层星超导增伤、C1 携带回能与冷却、C2 携带延长
    秒数、C6 携带层数上限与精通。
    """

    specs = (
        ("passive:4", "character.alyosha.passive.p4", "passive", "惊醒沉睡的林线", (999.0, 1.2)),
        (
            "passive:5",
            "character.alyosha.passive.p5",
            "passive",
            "告别冬麦与残叶",
            (0.01, 0.0035, 0.7),
        ),
        (
            "passive:6",
            "character.alyosha.passive.p6",
            "passive",
            "星赴险域",
            (999.0, 999.0, 0.2),
        ),
        (
            "passive_exploration:8",
            "character.alyosha.passive.p8",
            "passive_exploration",
            "树梢察伺",
            (),
        ),
        (
            "constellation:c1",
            "character.alyosha.constellation.c1",
            "constellation",
            "寒谷轰雷",
            (15.0, 18.0),
        ),
        (
            "constellation:c2",
            "character.alyosha.constellation.c2",
            "constellation",
            "长嗥远讯",
            (6.0, 999.0, 999.0),
        ),
        (
            "constellation:c3",
            "character.alyosha.constellation.c3",
            "constellation",
            "僚朋相唤",
            (3.0, 15.0),
        ),
        (
            "constellation:c4",
            "character.alyosha.constellation.c4",
            "constellation",
            "衔取猎品",
            (999.0, 0.6),
        ),
        (
            "constellation:c5",
            "character.alyosha.constellation.c5",
            "constellation",
            "莺啼止时",
            (3.0, 15.0),
        ),
        (
            "constellation:c6",
            "character.alyosha.constellation.c6",
            "constellation",
            "复夺旌幡",
            (999.0, 2.0, 2.0, 100.0),
        ),
    )
    return tuple(
        EffectPayload(
            effect_key=f"{ALYOSHA_CHARACTER_KEY}:{unlock_key}",
            owner_type="character",
            owner_key=ALYOSHA_CHARACTER_KEY,
            effect_kind=effect_kind,
            unlock_key=unlock_key,
            handler_key=handler_key,
            params={
                "schema_version": 1,
                "name": name,
                "components": tuple({"values": (value,)} for value in component_values),
            },
        )
        for unlock_key, handler_key, effect_kind, name, component_values in specs
    )
