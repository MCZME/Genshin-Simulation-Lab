"""桑多涅测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from genshin_sim.assets.models import EffectPayload, TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_FIRST_OFFSET_FRAMES,
    FAGEOU_RAY_INTERVAL_FRAMES,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
    SANDRONE_PASSIVE_P4_HANDLER_KEY,
    SANDRONE_PASSIVE_P5_HANDLER_KEY,
    SANDRONE_PASSIVE_P6_HANDLER_KEY,
    sandrone_tactics_definition_key,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    plan_radiance_buff_requests,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。characters 行、等级行、效果行与
# 效果键组合共用此键，保持夹具内部一致。
SANDRONE_CHARACTER_KEY = "character:sandrone_test"
SANDRONE_REF = AttributeSubjectRef.character("character:slot_1")


def c6_effect_params() -> dict[str, object]:
    """合成资产「命座第 6 层」效果行的 params（与资产库写入同一份数据）。"""

    for payload in _minimal_sandrone_effect_payloads():
        if payload.unlock_key == "c6":
            return dict(payload.params)
    raise AssertionError("合成效果行缺少命座第 6 层")


def write_sandrone_asset_database(
    db_path: Path,
    *,
    scaling_ratio_overrides: Mapping[str, float] | None = None,
) -> Path:
    """写入桑多涅单人最小合成资产库（倍率数值默认全部为 1.0）。

    ``scaling_ratio_overrides`` 按倍率条目 key 覆盖合成倍率：默认全 1.0 时
    「倍率区相加」与「倍率区相乘」在数值上不可区分，需要区分口径的用例必须
    给出非 1.0 的倍率。
    """

    from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats

    characters = (
        CharacterAsset(
            asset_key=SANDRONE_CHARACTER_KEY,
            source_id=SANDRONE_CHARACTER_KEY.removeprefix("character:"),
            name="桑多涅",
            element="cryo",
            weapon_type="claymore",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key=SANDRONE_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=SANDRONE_CHARACTER_KEY,
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
            "data_version": "sandrone-minimal-2",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sandrone-minimal",
            "source_version": "1",
            "content_hash": "sandrone-minimal-2",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_sandrone_scaling_entries(ratio_overrides=scaling_ratio_overrides),
        effect_payloads=_minimal_sandrone_effect_payloads(),
    )


def _minimal_sandrone_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回被动/命座集成测试需要的合成效果行（数值与名称均为合成数据）。

    效果行必须带 ``name``（资产转换器对命座行同样强制该字段）：内容单元用它做
    错误定位与审计显示名，合成的名称刻意与真实资产不同，避免测试跟着资产改名。
    """

    def _effect(
        effect_key: str,
        effect_kind: str,
        handler_key: str,
        unlock_key: str,
        values: tuple[float, ...],
        *,
        name: str,
    ) -> EffectPayload:
        return EffectPayload(
            effect_key=f"{SANDRONE_CHARACTER_KEY}:{effect_key}",
            owner_type="character",
            owner_key=SANDRONE_CHARACTER_KEY,
            effect_kind=effect_kind,
            unlock_key=unlock_key,
            handler_key=handler_key,
            params={
                "schema_version": 1,
                "name": name,
                "components": tuple(
                    {
                        "source_param": f"number_{index}",
                        "kind": "numeric",
                        "format": "number",
                        "values": (value,),
                    }
                    for index, value in enumerate(values, start=1)
                ),
            },
        )

    return (
        # P4/P6 的数值行为在角色单元内，均按位置读取数值，分量形状须与真实
        # 资产一致，否则解析错位：P4 前导为链接分量；P6 前两位为链接（极星
        # 辉域）与持续秒数，其后才是每 100 攻击 / 0.7% / 14%。
        _effect(
            "passive:4",
            "passive",
            SANDRONE_PASSIVE_P4_HANDLER_KEY,
            "passive:4",
            (11500004.0, 11332.0, 11330002.0, 50.0, 4.0, 10.0, 60.0, 10.0, 11335.0, 1.0, 0.1),
            name="合成天赋4",
        ),
        _effect(
            "passive:5",
            "passive",
            SANDRONE_PASSIVE_P5_HANDLER_KEY,
            "passive:5",
            (100.0, 8.0, 160.0),
            name="合成天赋5",
        ),
        _effect(
            "passive:6",
            "passive",
            SANDRONE_PASSIVE_P6_HANDLER_KEY,
            "passive:6",
            (11330003.0, 8.0, 100.0, 0.007, 0.14),
            name="合成天赋6",
        ),
        _effect(
            "constellation:c1",
            "constellation",
            SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
            "c1",
            (11330001.0, 11330002.0, 0.5, 0.3),
            name="合成命座1",
        ),
        _effect(
            "constellation:c2",
            "constellation",
            SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
            "c2",
            (0.4, 11330001.0, 0.2, 3.0),
            name="合成命座2",
        ),
        _effect(
            "constellation:c3",
            "constellation",
            SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
            "c3",
            (11331.0, 3.0, 15.0),
            name="合成命座3",
        ),
        _effect(
            "constellation:c4",
            "constellation",
            SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
            "c4",
            (1.25, 1.875, 4.0),
            name="合成命座4",
        ),
        _effect(
            "constellation:c5",
            "constellation",
            SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
            "c5",
            (11335.0, 3.0, 15.0),
            name="合成命座5",
        ),
        _effect(
            "constellation:c6",
            "constellation",
            SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
            "c6",
            # 与资产同序：链接 解算 / 段数 4 / 普通 100% / 段数 4（辉映段）
            # / 星超导 80% / 星扩散 120% / 链接 星烁擢升 / 擢升 20%。
            (11330001.0, 4.0, 1.0, 4.0, 0.8, 1.2, 11190007.0, 0.2),
            name="合成命座6",
        ),
    )


def minimal_sandrone_scaling_entries(
    *,
    ratio_overrides: Mapping[str, float] | None = None,
) -> tuple[TalentScalingEntry, ...]:
    """返回桑多涅 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足
    工厂编译；落地冲击条目需要低空/高空两个分量。``ratio_overrides`` 按
    ``entry_key`` 覆盖指定条目的合成倍率（默认全 1.0 会让倍率区的相加与
    相乘口径不可区分）。
    """

    overrides = dict(ratio_overrides or {})

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio",)),
        ("sweep", "normal_attack", "重击扫射伤害", ("plain_ratio",)),
        ("ray", "normal_attack", "重击冷凝射线伤害", ("plain_ratio",)),
        ("ray_stellar", "normal_attack", "重击冷凝射线星超导伤害", ("plain_ratio",)),
        ("ray_swirl", "normal_attack", "重击冷凝射线星扩散伤害", ("plain_ratio",)),
        ("overload", "normal_attack", "功率过载时伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("prism", "elemental_skill", "棱晶弹伤害", ("plain_ratio",)),
        ("prism_stellar", "elemental_skill", "棱晶弹星超导伤害", ("plain_ratio",)),
        ("prism_swirl", "elemental_skill", "棱晶弹星扩散伤害", ("plain_ratio",)),
        ("bombardment", "elemental_burst", "轰炸伤害", ("plain_ratio",)),
        ("beam", "elemental_burst", "聚能光束伤害", ("plain_ratio",)),
        ("beam_stellar", "elemental_burst", "聚能光束星超导伤害", ("plain_ratio",)),
        ("beam_swirl", "elemental_burst", "聚能光束星扩散伤害", ("plain_ratio",)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=SANDRONE_CHARACTER_KEY,
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
                        "values": tuple(overrides.get(entry_key, 1.0) for _ in range(15)),
                    }
                    for index, kind in enumerate(kinds)
                ),
            },
            tags=(talent_key,),
        )
        for entry_key, talent_key, label, kinds in specs
    )


def make_aura_application_impact(
    frame: int,
    element: Element,
    target_ref: str,
    request_id: str,
    *,
    owner_slot: int = 1,
) -> ImpactRequest:
    """构造一次最小元素附着影响请求，用于在仿真前种入 Aura 以触发反应。"""

    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key=f"test.sandrone.aura_application.{element.value}",
        owner_slot=owner_slot,
        request_id=request_id,
        target_refs=(target_ref,),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=f"{request_id}:spec",
            element=element,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )


def sandrone_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
    targets: list[dict[str, object]] | None = None,
    constellation: int = 0,
    level: int = 90,
) -> dict[str, object]:
    """桑多涅单人集成测试配置。"""

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
        "meta": {"name": "sandrone damage integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": SANDRONE_CHARACTER_KEY,
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


def sandrone_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def charged_line_payload(
    max_frames: int,
    press: int,
    release: int,
    *,
    constellation: int = 0,
) -> dict[str, object]:
    """重击直线场景：玩家原点朝 +Z，目标摆在 (0, 0, 4) 的射击直线上。

    重击 = 长按左键（按下即蓄力，按住时长需跨过前摇 36F）。
    """

    return sandrone_input_payload(
        max_frames=max_frames,
        constellation=constellation,
        input_trace=[
            {"frame": press, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": release, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )


def charged_ray_frames(press: int, count: int) -> list[int]:
    """按法洁欧节奏常量推导射线命中帧（首法 = 按下 + 90F，即时命中）。"""

    return [
        press + FAGEOU_RAY_FIRST_OFFSET_FRAMES + index * FAGEOU_RAY_INTERVAL_FRAMES
        for index in range(count)
    ]


def apply_radiance_buff(assembled, *, settled_stacks: int = 3, frame: int = 0) -> None:
    """按星超导协调的申请计划注入辉映·星烁 Buff（属性证据侧入口）。"""

    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    runtime.commit_prevalidated(
        runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=frame,
                occurrence_ref=f"integration:radiance:{frame}",
                character_refs=(SANDRONE_REF,),
                settled_stacks=settled_stacks,
                field_expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
    )


def resolved_atk(assembled) -> float:
    """解析桑多涅当前面板攻击力（供相对断言折算）。"""

    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(subject_ref=SANDRONE_REF, attribute_key=STAT_ATK_TOTAL, frame=1)
    )
    return float(resolution.final_value)


def tactics_stack_count(assembled, *, frame: int) -> int:
    """读取桑多涅改进战术 Buff 的活动层数（P4 层数断言口）。

    改进战术由状态效果系统承载（marker Buff），层数不再落角色状态字段；
    冲突键保证单条活动记录，此处按层数求和以防表达变化。
    """

    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    records = runtime.reader.active(
        frame,
        target_ref=SANDRONE_REF,
        definition_key=sandrone_tactics_definition_key(1),
    )
    return sum(record.state.stack_count for record in records)
