"""砂糖测试共享构造器：最小合成资产库、队友夹具与仿真输入辅助。

倍率与等级数值全部为测试自造的合成值，不复制任何真实资产数值：真实数值的
正确性由资产构建与校验链路承担，测试只验证接线所需的最小形状与命中帧/衔接
时序（见测试规范 §3.2）。四段普攻刻意取互不相同的合成倍率，用来验证
「资产倍率行 -> 命中契约 -> 动作影响点」的逐段接线。

固有天赋 A1 / A4 需要**队友**才能观测投放范围，因此这里额外提供：
① ``effect_payloads`` 形态的 A1 / A4 效果行（参数形状与真实资产一致，
数值为合成值）；② 一个零行为队友夹具角色（动作解释器恒等待），供需要
「同元素 / 异元素队友」的集成用例装配队伍。

「魔女的前夜礼」（``passive:9``）是**队伍级**机制，需要队伍里至少两名魔导
角色才激活，而本期只有砂糖一名角色会声明魔导标记，因此再提供：
③ 同一形状、但带魔导标记的**魔导队友夹具**（``mage_teammate_slots`` 指定哪些
槽位用魔导夹具）；④ ``passive:9`` 的合成效果行。生产环境只有一名魔导角色
时不激活属预期行为，不额外造特例。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import (
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
)
from genshin_sim.content import create_default_content_unit_registry
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_MASTERY_FLAT,
    SUCROSE_A4_MASTERY_RATIO,
    SUCROSE_ASSET_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C1_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C2_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C3_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C4_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C5_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_WITCHES_EVE_LARGE_BONUS,
    SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES,
    SUCROSE_WITCHES_EVE_MIN_MAGE_COUNT,
    SUCROSE_WITCHES_EVE_SMALL_BONUS,
    SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import (
    CharacterContentUnitRequest,
    ContentUnitRegistry,
)
from genshin_sim.content.team.mage import MAGE_MARKER_KEY
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    InputSessionView,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl import SWIRL_REACTION_KEY
from genshin_sim.core.systems.reaction.models import (
    ElementalTransitionEffect,
    ReactionOccurrence,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

SUCROSE_CHARACTER_KEY = SUCROSE_ASSET_KEY

# 队友夹具角色的稳定 handler_key：内容包不声明资产身份（见 D-079），夹具只提供
# 槽位身份与等待型动作解释器；集成用例需把它注册进内容单元注册表。
SUCROSE_TEAMMATE_HANDLER_KEY = "character.testing.sucrose_teammate_noop"
# 魔导队友夹具：与普通队友夹具同形，只是内容单元多声明一个魔导标记，供
# 「队伍魔导角色数 ≥2」的激活判定使用。
SUCROSE_MAGE_TEAMMATE_HANDLER_KEY = "character.testing.sucrose_mage_teammate_noop"


def sucrose_teammate_asset_key(slot: int, element: str) -> str:
    """队友夹具角色的资产键（按槽位与元素唯一）。"""

    return f"character:teammate_{element}_{slot}"


class SucroseTeammateActionInterpreter:
    """队友夹具的动作解释器：始终等待，不触发任何动作。"""

    supported_action_keys: tuple[str, ...] = ()

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        del context, session
        return ActionInterpretationResult.wait()


def create_sucrose_teammate_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """队友夹具角色的内容单元工厂：只提供槽位身份与等待型动作解释器。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version="dev-test",
        slot=request.slot,
        action_interpreter=SucroseTeammateActionInterpreter(),
        metadata={"purpose": "sucrose_teammate_fixture"},
    )


def create_sucrose_mage_teammate_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """魔导队友夹具：零行为，只在 metadata 上声明魔导资格标记。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version="dev-test",
        slot=request.slot,
        action_interpreter=SucroseTeammateActionInterpreter(),
        metadata={"purpose": "sucrose_mage_teammate_fixture", MAGE_MARKER_KEY: True},
    )


def sucrose_test_registry() -> ContentUnitRegistry:
    """默认内容注册表 + 队友夹具工厂（需要队友的集成用例共用入口）。"""

    registry = create_default_content_unit_registry()
    registry.register_character_factory(
        SUCROSE_TEAMMATE_HANDLER_KEY,
        create_sucrose_teammate_content_unit,
    )
    registry.register_character_factory(
        SUCROSE_MAGE_TEAMMATE_HANDLER_KEY,
        create_sucrose_mage_teammate_content_unit,
    )
    return registry


# 合成基础属性：只为让伤害公式能取到合法来源，不复制真实资产数值。
SUCROSE_BASE_HP = 10_000.0
SUCROSE_BASE_ATK = 200.0
SUCROSE_BASE_DEF = 600.0

# 各能力的合成倍率：普攻四段互不相同，用于逐段接线校验；重击/下落/战技/爆发
# 各取一个独立的合成值，用于验证「资产倍率行 -> 命中契约」的接线。
SUCROSE_FIXTURE_RATIOS = {
    "一段伤害": 1.0,
    "二段伤害": 2.0,
    "三段伤害": 3.0,
    "四段伤害": 4.0,
    "重击伤害": 5.0,
    "下坠期间伤害": 6.0,
    "低空/高空坠地冲击伤害": 7.0,
    "技能伤害": 8.0,
    "持续伤害": 9.0,
    "附加元素伤害": 10.0,
}


def write_sucrose_asset_database(
    db_path: Path,
    *,
    teammate_elements: tuple[str, ...] = (),
    sucrose_ascension_phase: int = 6,
    mage_teammate_slots: tuple[int, ...] = (),
) -> Path:
    """写入砂糖最小合成资产库（可附带队友夹具角色）。

    ``teammate_elements`` 按顺序占用槽位 2 / 3 / 4，元素取给定字符串；队友的
    handler_key 是 ``SUCROSE_TEAMMATE_HANDLER_KEY``，装配时需用
    ``sucrose_test_registry()`` 提供工厂。A1 / A4 的效果行随资产一并写入，
    因此单元资产库自身就能挂出两支固有天赋。

    ``mage_teammate_slots`` 指定哪些队友槽位改用**魔导**队友夹具
    （``SUCROSE_MAGE_TEAMMATE_HANDLER_KEY``）：该夹具只是多声明一个魔导标记，
    用来凑够「魔导·秘仪」的 ≥2 名门槛。不指定时队伍只有砂糖一名魔导角色，
    前夜礼按预期不激活。

    ``sucrose_ascension_phase`` 用于「突破阶段不足则不挂固有天赋」的接线验收：
    解锁判据读的就是等级属性行的突破阶段（见内容编译期 ``UnlockValues``）。
    """

    characters = [
        CharacterAsset(
            asset_key=SUCROSE_CHARACTER_KEY,
            source_id=SUCROSE_CHARACTER_KEY.removeprefix("character:"),
            name="砂糖",
            element="anemo",
            weapon_type="catalyst",
            rarity=4,
            burst_energy_cost=80.0,
            handler_key=SUCROSE_CHARACTER_HANDLER_KEY,
        )
    ]
    character_level_stats = [
        CharacterLevelStats(
            character_key=SUCROSE_CHARACTER_KEY,
            level=90,
            ascension_phase=sucrose_ascension_phase,
            base_hp=SUCROSE_BASE_HP,
            base_atk=SUCROSE_BASE_ATK,
            base_def=SUCROSE_BASE_DEF,
            ascension_stat="hp_percent",
            ascension_value=0.0,
        )
    ]
    for slot, element in enumerate(teammate_elements, start=2):
        asset_key = sucrose_teammate_asset_key(slot, element)
        handler_key = (
            SUCROSE_MAGE_TEAMMATE_HANDLER_KEY
            if slot in mage_teammate_slots
            else SUCROSE_TEAMMATE_HANDLER_KEY
        )
        characters.append(
            CharacterAsset(
                asset_key=asset_key,
                source_id=asset_key.removeprefix("character:"),
                name=f"队友 {element}",
                element=element,
                weapon_type="sword",
                rarity=4,
                burst_energy_cost=60.0,
                handler_key=handler_key,
            )
        )
        character_level_stats.append(
            CharacterLevelStats(
                character_key=asset_key,
                level=90,
                ascension_phase=6,
                base_hp=SUCROSE_BASE_HP,
                base_atk=SUCROSE_BASE_ATK,
                base_def=SUCROSE_BASE_DEF,
            )
        )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "sucrose-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sucrose-minimal",
            "source_version": "1",
            "content_hash": "sucrose-minimal-1",
        },
        characters=tuple(characters),
        character_level_stats=tuple(character_level_stats),
        talent_scalings=minimal_sucrose_scaling_entries(),
        effect_payloads=minimal_sucrose_effect_payloads(),
    )


def minimal_sucrose_effect_payloads() -> tuple[EffectPayload, ...]:
    """A1 / A4 / 前夜礼的合成效果行（参数形状与真实资产一致，数值为合成值）。

    绑定键取真实资产的 ``character:10000043:passive:4`` / ``passive:5`` /
    ``passive:9``，与本地资产库
    （``assets set-handler --kind effect --key character:10000043:passive:4``）
    的接线逐字一致，用例因此能覆盖「资产效果行 -> 效果工厂」这一环。

    前夜礼一行的五个分量依次是：魔导·秘仪门槛人数、小型风灵档秒数与比例、
    大型风灵档秒数与比例（与真实 ``passive:9`` 的 components 同序同形）。
    """

    return (
        EffectPayload(
            effect_key=f"{SUCROSE_CHARACTER_KEY}:passive:4",
            owner_type="character",
            owner_key=SUCROSE_CHARACTER_KEY,
            effect_kind="passive",
            unlock_key="passive:4",
            handler_key=SUCROSE_PASSIVE_A1_HANDLER_KEY,
            params=_effect_params("触媒置换术", (SUCROSE_A1_MASTERY_FLAT, 8.0)),
        ),
        EffectPayload(
            effect_key=f"{SUCROSE_CHARACTER_KEY}:passive:5",
            owner_type="character",
            owner_key=SUCROSE_CHARACTER_KEY,
            effect_kind="passive",
            unlock_key="passive:5",
            handler_key=SUCROSE_PASSIVE_A4_HANDLER_KEY,
            params=_effect_params("小小的慧风", (SUCROSE_A4_MASTERY_RATIO, 8.0)),
        ),
        EffectPayload(
            effect_key=f"{SUCROSE_CHARACTER_KEY}:passive:9",
            owner_type="character",
            owner_key=SUCROSE_CHARACTER_KEY,
            # 真实资产的 effect_kind 是 passive_exploration；内容侧与 A1 / A4
            # 同口径按 PASSIVE 声明，故这里仍写 passive。
            effect_kind="passive",
            unlock_key="passive:9",
            handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
            params=_effect_params(
                "魔女的前夜礼·七循之理",
                (
                    float(SUCROSE_WITCHES_EVE_MIN_MAGE_COUNT),
                    SUCROSE_WITCHES_EVE_SMALL_DURATION_FRAMES / 60,
                    SUCROSE_WITCHES_EVE_SMALL_BONUS,
                    SUCROSE_WITCHES_EVE_LARGE_DURATION_FRAMES / 60,
                    SUCROSE_WITCHES_EVE_LARGE_BONUS,
                ),
            ),
        ),
        *_constellation_payloads(),
    )


def _constellation_payloads() -> tuple[EffectPayload, ...]:
    """命座 c1–c6 的合成效果行（参数形状与真实资产一致，数值为合成值）。

    各层分量与真实资产同序：``c1 = [次数]``、``c2 = [秒]``、``c3 / c5 =
    [等级, 上限]``、``c4 = [次数, 下限, 上限, 计次秒]``（源站以负值表示减少）、
    ``c6 = [比例]``。
    """

    rows = (
        ("c1", SUCROSE_CONSTELLATION_C1_HANDLER_KEY, "堆叠真空域", (1.0,)),
        ("c2", SUCROSE_CONSTELLATION_C2_HANDLER_KEY, "不羁型贝特", (2.0,)),
        ("c3", SUCROSE_CONSTELLATION_C3_HANDLER_KEY, "零失误少女", (3.0, 15.0)),
        ("c4", SUCROSE_CONSTELLATION_C4_HANDLER_KEY, "炼金的偏执", (7.0, 1.0, -7.0, 0.1)),
        ("c5", SUCROSE_CONSTELLATION_C5_HANDLER_KEY, "认真普通瓶", (3.0, 15.0)),
        ("c6", SUCROSE_CONSTELLATION_C6_HANDLER_KEY, "混元熵增论", (0.2,)),
    )
    return tuple(
        EffectPayload(
            effect_key=f"{SUCROSE_CHARACTER_KEY}:constellation:{unlock_key}",
            owner_type="character",
            owner_key=SUCROSE_CHARACTER_KEY,
            effect_kind="constellation",
            unlock_key=unlock_key,
            handler_key=handler_key,
            params=_effect_params(name, values),
        )
        for unlock_key, handler_key, name, values in rows
    )


def _effect_params(name: str, values: tuple[float, ...]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": name,
        "components": tuple(
            {"kind": "numeric", "format": "number", "values": [value]} for value in values
        ),
    }


def make_swirl_occurrence(
    *,
    source_key: str = "character:slot_1",
    aura_kind: AuraKind = AuraKind.PYRO,
    reaction_key: str = SWIRL_REACTION_KEY,
    occurrence_ref: str = "occurrence:sucrose.swirl",
) -> ReactionOccurrence:
    """构造砂糖触发的扩散 / 星扩散反应事实替身。

    A1 只消费反应键、发生源与 ``transition.aura_kind``，其余字段取最小合法值；
    星扩散与普通扩散共用同一形状，差别只在 ``reaction_key``。
    """

    return ReactionOccurrence(
        occurrence_ref=occurrence_ref,
        interaction_id=f"interaction:{occurrence_ref}",
        reaction_key=reaction_key,
        direction_key=f"{aura_kind.value}+anemo",
        profile_key=f"profile:{reaction_key}",
        source_ref=ElementalSourceRef(source_key),
        subject_ref=ElementalSubjectRef.target("target:1"),
        transition=ElementalTransitionEffect(
            aura_kind=aura_kind,
            incoming_before=AuraAmount.one(),
            incoming_consumed=AuraAmount.one(),
            incoming_remaining=AuraAmount.zero(),
            aura_before=AuraAmount.one(),
            aura_consumed=AuraAmount.one(),
            aura_remaining=AuraAmount.zero(),
        ),
    )


# 星扩散：与普通扩散共用同一事实形状，供「触发集合含星扩散」的用例引用。
SUCROSE_FIXTURE_STELLAR_SWIRL_REACTION_KEY = STELLAR_SWIRL_REACTION_KEY


def minimal_sucrose_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回砂糖内容工厂接线所需的最小倍率行。

    分量形状与真实资产一致（普攻四段/重击/战技/爆发两行各 1 分量、落地冲击
    2 分量），数值取合成倍率表；等级区间取 1–15 覆盖天赋等级解析。
    """

    specs = (
        ("normal_attack", "一段伤害", (SUCROSE_FIXTURE_RATIOS["一段伤害"],)),
        ("normal_attack", "二段伤害", (SUCROSE_FIXTURE_RATIOS["二段伤害"],)),
        ("normal_attack", "三段伤害", (SUCROSE_FIXTURE_RATIOS["三段伤害"],)),
        ("normal_attack", "四段伤害", (SUCROSE_FIXTURE_RATIOS["四段伤害"],)),
        ("normal_attack", "重击伤害", (SUCROSE_FIXTURE_RATIOS["重击伤害"],)),
        ("normal_attack", "下坠期间伤害", (SUCROSE_FIXTURE_RATIOS["下坠期间伤害"],)),
        (
            "normal_attack",
            "低空/高空坠地冲击伤害",
            (SUCROSE_FIXTURE_RATIOS["低空/高空坠地冲击伤害"],) * 2,
        ),
        ("elemental_skill", "技能伤害", (SUCROSE_FIXTURE_RATIOS["技能伤害"],)),
        ("elemental_burst", "持续伤害", (SUCROSE_FIXTURE_RATIOS["持续伤害"],)),
        ("elemental_burst", "附加元素伤害", (SUCROSE_FIXTURE_RATIOS["附加元素伤害"],)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=SUCROSE_CHARACTER_KEY,
            talent_key=talent_key,
            entry_key=f"{talent_key}_{index}",
            label=label,
            scaling={
                "schema_version": 1,
                "mode": "level_table",
                "level_min": 1,
                "level_max": 15,
                "components": tuple(
                    {
                        "source_param": f"param_{position}",
                        "kind": "plain_ratio",
                        "values": tuple(value for _ in range(15)),
                    }
                    for position, value in enumerate(values)
                ),
            },
            tags=(talent_key,),
        )
        for index, (talent_key, label, values) in enumerate(specs)
    )


def single_target_scene() -> dict[str, object]:
    """场景中的单个 90 级测试目标。"""

    return {
        "targets": [
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            },
        ]
    }


def sucrose_input_payload(
    *,
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 60,
    targets: tuple[dict[str, object], ...] | None = None,
    full_energy: bool = False,
    teammate_elements: tuple[str, ...] = (),
    mastery: float = 0.0,
    constellation: int = 0,
) -> dict[str, object]:
    """砂糖单人集成测试配置。缺省为一次普攻一段。

    ``full_energy`` 打开 ``start_with_full_energy`` 规则：元素爆发有 80 点爆发
    能量门槛，缺省零能量下施放会被公共条件端口拒绝。

    ``teammate_elements`` 与 ``write_sucrose_asset_database`` 的参数一一对应
    （槽位 2 / 3 / 4）。``mastery`` 给砂糖挂一份合成元素精通词条（圣遗物
    面板词条），A4 的「按砂糖快照精通折算」由此可观测。队友不需要精通来源。

    ``constellation`` 为砂糖的命座层数：命座单元的解锁判据读的就是它，C1 / C2
    的静态切片（充能数、爆发时长）也由它门控。
    """

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
        ]
    team: list[dict[str, object]] = [
        {
            "slot": 1,
            "character": {
                "asset_key": SUCROSE_CHARACTER_KEY,
                "level": 90,
                "constellation": constellation,
                "talents": {
                    "normal_attack": 1,
                    "elemental_skill": 1,
                    "elemental_burst": 1,
                },
            },
            "artifacts": {
                "sets": [],
                "stats": {"elemental_mastery": mastery} if mastery else {},
            },
        }
    ]
    for slot, element in enumerate(teammate_elements, start=2):
        team.append(
            {
                "slot": slot,
                "character": {
                    "asset_key": sucrose_teammate_asset_key(slot, element),
                    "level": 90,
                    "constellation": 0,
                    "talents": {"normal_attack": 1},
                },
                "artifacts": {"sets": [], "stats": {}},
            }
        )
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "sucrose integration", "description": ""},
        "team": team,
        "scene": {"targets": list(targets)} if targets else single_target_scene(),
        "input_trace": input_trace,
        "rules": {"active": ["start_with_full_energy"] if full_energy else []},
        "run_options": {"max_frames": max_frames},
    }


def press_release(frame: int, key: str = "mouse.left") -> list[dict[str, object]]:
    """构造一次 press/release 输入事件对（release 在下一帧）。"""

    return [
        {"frame": frame, "events": [{"key": key, "phase": "press"}]},
        {"frame": frame + 1, "events": [{"key": key, "phase": "release"}]},
    ]


def sucrose_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events
