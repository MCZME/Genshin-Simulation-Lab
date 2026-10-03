"""奥黛塔测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from genshin_sim.assets.models import EffectPayload, TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CONSTELLATION_C1_HANDLER_KEY,
    ODETTE_CONSTELLATION_C2_HANDLER_KEY,
    ODETTE_CONSTELLATION_C3_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    ODETTE_CONSTELLATION_C5_HANDLER_KEY,
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
    ODETTE_PASSIVE_P8_HANDLER_KEY,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.actions import (
    ActionInterpretationContext,
    ActionInterpretationResult,
    InputSessionView,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。characters 行、等级行、效果行与
# 效果键组合共用此键，保持夹具内部一致。
ODETTE_CHARACTER_KEY = "character:odette_test"
ODETTE_REF = AttributeSubjectRef.character("character:slot_1")

# 陪测角色（华彩转交等多角色队伍用例）的测试 handler 键。动作输入校验要求
# 全部队伍槽位都提供动作解释器，内置 noop 占位不带解释器，因此陪测角色必须
# 单独注册内容单元工厂。
ODETTE_COMPANION_HANDLER_KEY = "character.testing.odette_companion_noop"


class OdetteCompanionActionInterpreter:
    """陪测角色动作解释器：始终等待，不产生任何动作。"""

    supported_action_keys: tuple[str, ...] = ()

    def interpret(
        self,
        context: ActionInterpretationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        del context, session
        return ActionInterpretationResult.wait()


def create_odette_companion_content_unit(
    request: CharacterContentUnitRequest,
) -> ContentUnit:
    """陪测角色内容单元工厂：只提供槽位身份与等待型动作解释器。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key=request.character_key,
        handler_key=request.handler_key,
        version="dev-test",
        slot=request.slot,
        action_interpreter=OdetteCompanionActionInterpreter(),
        metadata={"purpose": "odette_companion_fixture"},
    )


def write_odette_asset_database(
    db_path: Path,
    *,
    scaling_ratio_overrides: Mapping[str, float] | None = None,
    companions: int = 0,
) -> Path:
    """写入奥黛塔最小合成资产库（倍率数值默认全部为 1.0）。

    ``companions`` 按槽位 2..N+1 追加陪测角色（``character.testing.odette_
    companion_noop``，由 ``create_odette_companion_content_unit`` 提供等待型
    动作解释器），用于华彩转交等多角色队伍用例；装配时必须注册该工厂。
    ``scaling_ratio_overrides`` 按倍率条目 key 覆盖合成倍率：默认全 1.0 时
    「倍率区相加」与「倍率区相乘」在数值上不可区分，需要区分口径的用例必须
    给出非 1.0 的倍率。
    """

    from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats
    from tests.helpers.team_assets import make_character_asset

    def _companion(slot: int):
        return make_character_asset(
            slot,
            "hydro",
            handler_key=ODETTE_COMPANION_HANDLER_KEY,
        )

    characters = (
        CharacterAsset(
            asset_key=ODETTE_CHARACTER_KEY,
            source_id=ODETTE_CHARACTER_KEY.removeprefix("character:"),
            name="奥黛塔",
            element="cryo",
            weapon_type="sword",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key=ODETTE_CHARACTER_HANDLER_KEY,
        ),
        *(_companion(slot) for slot in range(2, 2 + companions)),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=ODETTE_CHARACTER_KEY,
            level=90,
            ascension_phase=6,
            base_hp=10_000.0,
            base_atk=200.0,
            base_def=600.0,
            ascension_stat="crit_damage",
            ascension_value=0.0,
        ),
        *(
            CharacterLevelStats(
                character_key=_companion(slot).asset_key,
                level=90,
                ascension_phase=6,
                base_hp=10_000.0,
                base_atk=200.0,
                base_def=600.0,
                ascension_stat="crit_damage",
                ascension_value=0.0,
            )
            for slot in range(2, 2 + companions)
        ),
    )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "odette-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-odette-minimal",
            "source_version": "1",
            "content_hash": "odette-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_odette_scaling_entries(ratio_overrides=scaling_ratio_overrides),
        effect_payloads=minimal_odette_effect_payloads(),
    )


def minimal_odette_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回效果行绑定所需的最小合成效果行（数值与名称均为合成数据）。

    效果行 handler 键与真实绑定一致（``character.odette.*``），行为单元按
    切片落地（bootstrap 当前注册 UNIMPLEMENTED/EMPTY 占位）；本表保证装配
    链路按真实键走通。
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
            effect_key=f"{ODETTE_CHARACTER_KEY}:{effect_key}",
            owner_type="character",
            owner_key=ODETTE_CHARACTER_KEY,
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
        _effect(
            "passive:4",
            "passive",
            ODETTE_PASSIVE_P4_HANDLER_KEY,
            "passive:4",
            # 组件位对齐真实资产行：number_2 为华彩发放层数（number_1/3 为
            # 文本内词条链接编号，行为代码不消费）。
            (1.0, 4.0, 1.0),
            name="合成天赋4",
        ),
        _effect(
            "passive:5",
            "passive",
            ODETTE_PASSIVE_P5_HANDLER_KEY,
            "passive:5",
            (1000.0, 100.0, 0.015, 0.3),
            name="合成天赋5",
        ),
        _effect(
            "passive:6",
            "passive",
            ODETTE_PASSIVE_P6_HANDLER_KEY,
            "passive:6",
            (100.0, 0.007, 0.14),
            name="合成天赋6",
        ),
        _effect(
            "passive_exploration:8",
            "passive_exploration",
            ODETTE_PASSIVE_P8_HANDLER_KEY,
            "passive:8",
            (),
            name="合成天赋8",
        ),
        _effect(
            "constellation:c1",
            "constellation",
            ODETTE_CONSTELLATION_C1_HANDLER_KEY,
            "c1",
            # 组件位对齐真实资产行：number_5 为华彩额外叠层、number_7 为
            # 后台清除层数/秒；number_2/3 为 C1 追加段倍率（切片 6 消费），
            # 其余为词条链接编号占位。
            (1.0, 3.0, 4.0, 1.0, 2.0, 1.0, 2.0),
            name="合成命座1",
        ),
        _effect(
            "constellation:c2",
            "constellation",
            ODETTE_CONSTELLATION_C2_HANDLER_KEY,
            "c2",
            # 组件位对齐真实资产行：number_2 为每层攻击力提升、number_5 为
            # 减抗（切片 6 消费），其余为词条链接编号占位。
            (1.0, 0.07, 1.0, 1.0, 0.2),
            name="合成命座2",
        ),
        _effect(
            "constellation:c3",
            "constellation",
            ODETTE_CONSTELLATION_C3_HANDLER_KEY,
            "c3",
            (3.0, 15.0),
            name="合成命座3",
        ),
        _effect(
            "constellation:c4",
            "constellation",
            ODETTE_CONSTELLATION_C4_HANDLER_KEY,
            "c4",
            (0.5, 0.66, 0.99),
            name="合成命座4",
        ),
        _effect(
            "constellation:c5",
            "constellation",
            ODETTE_CONSTELLATION_C5_HANDLER_KEY,
            "c5",
            (3.0, 15.0),
            name="合成命座5",
        ),
        _effect(
            "constellation:c6",
            "constellation",
            ODETTE_CONSTELLATION_C6_HANDLER_KEY,
            "c6",
            # 组件位对齐真实资产行：number_3 为持有者擢升、number_4 为奥黛塔
            # 额外擢升，前两位为词条链接编号占位。
            (1.0, 1.0, 0.25, 0.2),
            name="合成命座6",
        ),
    )


def minimal_odette_scaling_entries(
    *,
    ratio_overrides: Mapping[str, float] | None = None,
) -> tuple[TalentScalingEntry, ...]:
    """返回奥黛塔 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足工厂
    编译；三段伤害与落地冲击条目需要两个分量。``ratio_overrides`` 按
    ``entry_key`` 覆盖指定条目的合成倍率。
    """

    overrides = dict(ratio_overrides or {})

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio", "plain_ratio")),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",)),
        ("na_5", "normal_attack", "五段伤害", ("plain_ratio",)),
        ("ca", "normal_attack", "重击伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("skill", "elemental_skill", "技能伤害", ("plain_ratio",)),
        ("dot", "elemental_skill", "破晓终奏持续伤害", ("plain_ratio",)),
        (
            "special_stellar",
            "elemental_skill",
            "破晓终奏星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("plume", "elemental_skill", "拂羽舞步伤害", ("plain_ratio",)),
        (
            "plume_stellar",
            "elemental_skill",
            "拂羽舞步星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("wing", "elemental_skill", "旋翼舞步伤害", ("plain_ratio",)),
        (
            "wing_stellar",
            "elemental_skill",
            "旋翼舞步星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("burst_slash", "elemental_burst", "斩击伤害", ("plain_ratio",)),
        ("burst_final", "elemental_burst", "斩击最终段伤害", ("plain_ratio",)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=ODETTE_CHARACTER_KEY,
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


def odette_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
    targets: list[dict[str, object]] | None = None,
    constellation: int = 0,
    level: int = 90,
    companions: int = 0,
) -> dict[str, object]:
    """奥黛塔单人集成测试配置。

    ``companions`` 与 ``write_odette_asset_database(companions=...)`` 配套：
    槽位 2..N+1 放置通用测试角色（资产键 ``character:hydro_<slot>``，与
    ``make_character_asset`` 的键规则一致）。
    """

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
    team: list[dict[str, object]] = [
        {
            "slot": 1,
            "character": {
                "asset_key": ODETTE_CHARACTER_KEY,
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
    ]
    for slot in range(2, 2 + companions):
        team.append(
            {
                "slot": slot,
                "character": {
                    "asset_key": f"character:hydro_{slot}",
                    "level": level,
                    "constellation": 0,
                    "talents": {
                        "normal_attack": 1,
                        "elemental_skill": 1,
                        "elemental_burst": 1,
                    },
                },
                "artifacts": {"sets": [], "stats": {}},
            }
        )
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "odette integration", "description": ""},
        "team": team,
        "scene": {"targets": targets},
        "input_trace": input_trace,
        "rules": {"active": []},
        "run_options": {"max_frames": max_frames},
    }


def odette_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def apply_radiance_buff(assembled, *, settled_stacks: int = 3, frame: int = 0) -> None:
    """按星超导协调的申请计划注入辉映·星烁 Buff（属性证据侧入口）。"""

    from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
        plan_radiance_buff_requests,
    )
    from genshin_sim.core.systems.buff import BuffRuntime
    from genshin_sim.core.systems.reaction.states import (
        STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    )

    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    runtime.commit_prevalidated(
        runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=frame,
                occurrence_ref=f"integration:radiance:{frame}",
                character_refs=(ODETTE_REF,),
                settled_stacks=settled_stacks,
                field_expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
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
        impact_key=f"test.odette.aura_application.{element.value}",
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
