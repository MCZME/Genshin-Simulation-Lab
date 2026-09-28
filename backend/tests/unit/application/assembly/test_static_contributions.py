"""内容静态贡献（天赋提升/冷却时长 term）与运行时绑定 provider 的装配测试。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.assembly.ports import TargetBuffPresenceReadAdapter
from genshin_sim.application.assembly.stages.content_compiler import ContentCompiler
from genshin_sim.application.assembly.stages.runtime_assembler import RuntimeAssembler
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.definitions.effects import (
    EffectKind,
    EffectSpec,
    UnlockKind,
    UnlockSpec,
)
from genshin_sim.content.registries import CharacterContentUnitRequest
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.cooldown import (
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownDurationTerm,
    CooldownKey,
    CooldownSubjectRef,
)


def _effect(threshold: int) -> EffectSpec:
    return EffectSpec(
        effect_key=f"character:test:constellation:c{threshold}",
        kind=EffectKind.CONSTELLATION,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=threshold),
    )


def _unit(*, threshold: int) -> ContentUnit:
    key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_skill",
    )
    term = CooldownDurationTerm(
        term_key="test.cooldown_reduction",
        source_ref="character.test",
        stage=CooldownDurationStage.OWNER_ADJUSTMENT,
        operation=CooldownDurationOperation.MULTIPLY_CURRENT,
        value=Decimal("0.85"),
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.constellation",
        version="dev-test",
        slot=1,
        effects=(_effect(threshold),),
        talent_level_boosts={"elemental_skill": 3},
        cooldown_duration_terms={key: (term,)},
        attribute_providers=(cast(Any, object()),),
    )


class _FakeLevelStats:
    ascension_phase = 0


class _FakeBundle:
    def __init__(self) -> None:
        self.character_level_stats = _FakeLevelStats()


class _FakeCharacter:
    asset_key = "character:test"


class _FakeWeapon:
    asset_key = "weapon:test"


class _FakeEffectPayload:
    def __init__(
        self,
        *,
        unlock_key: object,
        params: dict[str, object],
        owner_key: str = "character:test",
        owner_type: str = "character",
    ) -> None:
        self.unlock_key = unlock_key
        self.params = params
        self.owner_key = owner_key
        self.owner_type = owner_type


class _FakeBundleWithEffects(_FakeBundle):
    def __init__(self) -> None:
        super().__init__()
        self.character = _FakeCharacter()
        self.weapon = None
        self.artifact_sets = ()
        self.effect_payloads = (
            _FakeEffectPayload(unlock_key="c6", params={"schema_version": 1, "components": ()}),
            _FakeEffectPayload(unlock_key="c1", params={"schema_version": 1, "components": ()}),
            # 其他拥有者的效果行不进入：C6 数值不属于武器。
            _FakeEffectPayload(
                unlock_key="refine:1",
                params={"schema_version": 1},
                owner_key="weapon:test",
                owner_type="weapon",
            ),
            # 缺失 unlock_key 的效果行无法定位，跳过。
            _FakeEffectPayload(unlock_key=None, params={"schema_version": 1}),
        )


class _FakeCharacterConfig:
    def __init__(self, *, constellation: int) -> None:
        self.constellation = constellation
        self.talents = {"elemental_skill": 1}


class _FakeSlotConfig:
    def __init__(self, *, constellation: int) -> None:
        self.character = _FakeCharacterConfig(constellation=constellation)
        self.weapon = None
        self.artifacts = _FakeArtifacts()


class _FakeArtifacts:
    sets = ()


def test_character_effect_params_indexes_owner_rows_by_unlock_key():
    params = ContentCompiler._character_effect_params(cast(Any, _FakeBundleWithEffects()))

    assert sorted(params) == ["c1", "c6"]
    assert params["c6"]["schema_version"] == 1


def test_owner_contexts_carry_the_character_effect_rows():
    contexts = ContentCompiler._owner_contexts(
        cast(Any, _FakeBundleWithEffects()),
        cast(Any, _FakeSlotConfig(constellation=6)),
        character_effect_params={"c6": {"schema_version": 1}},
    )

    context = contexts[("character", "character:test")]
    assert context.constellation == 6
    assert context.effect_params == {"c6": {"schema_version": 1}}


def test_gate_static_slices_keeps_unlocked_static_contributions():
    unit = _unit(threshold=2)
    gated = ContentCompiler._gate_static_slices(
        unit,
        cast(Any, _FakeBundle()),
        cast(Any, _FakeSlotConfig(constellation=2)),
    )

    assert gated.talent_level_boosts == {"elemental_skill": 3}
    assert len(gated.cooldown_duration_terms) == 1
    assert len(gated.attribute_providers) == 1


def test_gate_static_slices_clears_locked_static_contributions_but_keeps_unit():
    unit = _unit(threshold=2)
    gated = ContentCompiler._gate_static_slices(
        unit,
        cast(Any, _FakeBundle()),
        cast(Any, _FakeSlotConfig(constellation=1)),
    )

    assert gated.talent_level_boosts == {}
    assert gated.cooldown_duration_terms == {}
    assert gated.attribute_providers == ()
    assert len(gated.effects) == 1
    assert gated.handler_key == unit.handler_key


def test_collect_talent_boosts_merges_distinct_keys_and_rejects_duplicates():
    first = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c3",
        version="dev-test",
        slot=1,
        talent_level_boosts={"elemental_burst": 3},
    )
    second = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c5",
        version="dev-test",
        slot=1,
        talent_level_boosts={"elemental_skill": 3},
    )

    assert ContentCompiler._collect_talent_boosts((first, second)) == {
        "elemental_burst": 3,
        "elemental_skill": 3,
    }

    duplicate = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c3",
        version="dev-test",
        slot=1,
        talent_level_boosts={"elemental_burst": 3},
    )
    with pytest.raises(InvalidRuntimePayloadError, match="多个等级提升来源"):
        ContentCompiler._collect_talent_boosts((first, duplicate))


def test_collect_cooldown_duration_terms_validates_owner_and_duplicates():
    unit = _unit(threshold=2)
    collected = ContentCompiler._collect_cooldown_duration_terms(
        (unit,),
        slot=1,
    )
    assert len(collected) == 1
    (key, terms) = next(iter(collected.items()))
    assert key.subject.subject_id == "character:slot_1"
    assert terms[0].term_key == "test.cooldown_reduction"

    foreign = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c2",
        version="dev-test",
        slot=1,
        cooldown_duration_terms={
            CooldownKey(
                CooldownSubjectRef.character("character:slot_2"),
                "elemental_skill",
            ): (terms[0],),
        },
    )
    with pytest.raises(InvalidRuntimePayloadError, match="归属不符"):
        ContentCompiler._collect_cooldown_duration_terms((foreign,), slot=1)

    duplicate = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c2",
        version="dev-test",
        slot=1,
        cooldown_duration_terms={
            key: (terms[0], terms[0]),
        },
    )
    with pytest.raises(InvalidRuntimePayloadError, match="重复 duration term"):
        ContentCompiler._collect_cooldown_duration_terms((duplicate,), slot=1)


class _FakeProvider:
    def __init__(self) -> None:
        self.bound_ports: tuple[object, object] | None = None

    def bind_runtime_ports(
        self,
        *,
        created_object_runtime: object,
        team_state: object,
    ) -> None:
        self.bound_ports = (created_object_runtime, team_state)


class _FakeContentBundle:
    def __init__(self, content_units: tuple[ContentUnit, ...]) -> None:
        self.content_units = content_units


def test_assembler_binds_runtime_attribute_provider_ports():
    provider = _FakeProvider()
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c2",
        version="dev-test",
        slot=1,
        attribute_providers=(cast(Any, provider),),
    )
    team_state = object()
    created_object_runtime = object()

    RuntimeAssembler._bind_attribute_provider_ports(
        cast(Any, _FakeContentBundle((unit,))),
        team_state=cast(Any, team_state),
        created_object_runtime=cast(Any, created_object_runtime),
    )

    assert provider.bound_ports == (created_object_runtime, team_state)


def test_assembler_binding_reports_provider_failure():
    class _BrokenProvider:
        def bind_runtime_ports(self, **kwargs: object) -> None:
            del kwargs
            raise RuntimeError("boom")

    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test.c2",
        version="dev-test",
        slot=1,
        attribute_providers=(cast(Any, _BrokenProvider()),),
    )

    with pytest.raises(InvalidRuntimePayloadError, match="绑定失败"):
        RuntimeAssembler._bind_attribute_provider_ports(
            cast(Any, _FakeContentBundle((unit,))),
            team_state=cast(Any, object()),
            created_object_runtime=cast(Any, object()),
        )


class _FakeBuffReader:
    """最小 Buff 只读查询替身，记录收到的查询参数。"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, Any, str]] = []

    def active(
        self,
        frame: int,
        target_ref: Any = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
    ) -> tuple[object, ...]:
        del mechanic_key
        self.calls.append((frame, target_ref, cast(str, definition_key)))
        return ()


class _FakeBindable:
    """声明可选端口绑定的内容对象替身；provider 与事件钩子共用同一形参契约。"""

    def __init__(self) -> None:
        self.bound_port: object | None = None

    def bind_runtime_ports(self, *, target_status_port: object) -> None:
        self.bound_port = target_status_port


def test_assembler_binds_runtime_damage_provider_ports():
    """内容伤害 provider 在装配期拿到目标状态只读端口，且该端口确实转发到 Buff 查询。"""

    provider = _FakeBindable()
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key="artifact_set:test",
        handler_key="artifact.test",
        version="dev-test",
        slot=1,
        damage_modifier_providers=(cast(Any, provider),),
    )
    reader = _FakeBuffReader()

    RuntimeAssembler._bind_content_runtime_ports(
        cast(Any, _FakeContentBundle((unit,))),
        buff_reader=cast(Any, reader),
    )

    assert isinstance(provider.bound_port, TargetBuffPresenceReadAdapter)
    target_ref = AttributeSubjectRef.target("target:star")
    assert (
        cast(Any, provider.bound_port).has_buff(
            target_ref=target_ref,
            definition_key="buff.reaction.superconduct.physical_resistance_reduction",
            frame=7,
        )
        is False
    )
    assert reader.calls == [
        (7, target_ref, "buff.reaction.superconduct.physical_resistance_reduction")
    ]


def test_assembler_binds_runtime_event_hook_ports():
    """声明了 bind_runtime_ports 的事件钩子同样在装配期拿到目标状态只读端口。"""

    hook = _FakeBindable()
    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key="weapon:test",
        handler_key="weapon.test.passive",
        version="dev-test",
        slot=1,
        event_hooks=(cast(Any, hook),),
    )

    RuntimeAssembler._bind_content_runtime_ports(
        cast(Any, _FakeContentBundle((unit,))),
        buff_reader=cast(Any, _FakeBuffReader()),
    )

    assert isinstance(hook.bound_port, TargetBuffPresenceReadAdapter)


def test_target_buff_presence_adapter_sums_active_stack_count():
    """``active_stack_count`` 返回匹配记录的活动层数之和，无匹配记录时为 0。"""

    class _FakeStackRecord:
        def __init__(self, stack_count: int) -> None:
            self.state = _FakeStackState(stack_count)

    class _FakeStackState:
        def __init__(self, stack_count: int) -> None:
            self.stack_count = stack_count

    class _FakeLayeredBuffReader:
        def __init__(self, records: tuple[object, ...]) -> None:
            self._records = records

        def active(
            self,
            frame: int,
            target_ref: Any = None,
            definition_key: str | None = None,
            mechanic_key: str | None = None,
        ) -> tuple[object, ...]:
            del frame, target_ref, definition_key, mechanic_key
            return self._records

    target_ref = AttributeSubjectRef.character("character:slot_1")

    assert (
        TargetBuffPresenceReadAdapter(
            cast(Any, _FakeLayeredBuffReader((_FakeStackRecord(3),)))
        ).active_stack_count(
            target_ref=target_ref,
            definition_key="buff.layered.test",
            frame=5,
        )
        == 3
    )
    assert (
        TargetBuffPresenceReadAdapter(cast(Any, _FakeLayeredBuffReader(()))).active_stack_count(
            target_ref=target_ref,
            definition_key="buff.layered.test",
            frame=5,
        )
        == 0
    )


def test_assembler_damage_binding_skips_providers_without_binder():
    """未声明 ``bind_runtime_ports`` 的伤害 provider 被跳过，不影响装配。"""

    class _PlainProvider:
        pass

    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key="artifact_set:test",
        handler_key="artifact.test",
        version="dev-test",
        slot=1,
        damage_modifier_providers=(cast(Any, _PlainProvider()),),
    )

    RuntimeAssembler._bind_content_runtime_ports(
        cast(Any, _FakeContentBundle((unit,))),
        buff_reader=cast(Any, _FakeBuffReader()),
    )


def test_assembler_damage_binding_reports_provider_failure():
    class _BrokenProvider:
        def bind_runtime_ports(self, **kwargs: object) -> None:
            del kwargs
            raise RuntimeError("boom")

    unit = ContentUnit(
        owner_type=ContentUnitOwnerType.ARTIFACT,
        owner_key="artifact_set:test",
        handler_key="artifact.test",
        version="dev-test",
        slot=1,
        damage_modifier_providers=(cast(Any, _BrokenProvider()),),
    )

    with pytest.raises(InvalidRuntimePayloadError, match="绑定失败"):
        RuntimeAssembler._bind_content_runtime_ports(
            cast(Any, _FakeContentBundle((unit,))),
            buff_reader=cast(Any, _FakeBuffReader()),
        )


def test_static_capability_port_exposes_sandrone_stellar_providers():
    """桑多涅随内容单元声明的星超导/星扩散 capability 经静态端口暴露。"""

    from genshin_sim.application.assembly.reaction_capabilities import (
        build_static_reaction_eligibility_port,
    )
    from genshin_sim.content.characters.snezhnaya.sandrone.content import (
        create_sandrone_content_unit,
    )
    from genshin_sim.core.elements import ElementalSubjectRef
    from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
        STELLAR_CONDUCT_CAPABILITY_KEY,
    )
    from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
        STELLAR_SWIRL_CAPABILITY_KEY,
    )
    from tests.helpers import sandrone as sandrone_helpers

    unit = create_sandrone_content_unit(
        CharacterContentUnitRequest(
            handler_key=sandrone_helpers.SANDRONE_CHARACTER_HANDLER_KEY,
            character_key=sandrone_helpers.SANDRONE_CHARACTER_KEY,
            slot=1,
            talent_levels={"normal_attack": 1, "elemental_skill": 1, "elemental_burst": 1},
            talent_scalings=sandrone_helpers.minimal_sandrone_scaling_entries(),
        )
    )
    port = build_static_reaction_eligibility_port((unit,))
    provider = ElementalSubjectRef.character("character:slot_1")
    for capability_key in (STELLAR_CONDUCT_CAPABILITY_KEY, STELLAR_SWIRL_CAPABILITY_KEY):
        assert port.evidence_for(frame=0, team_ref="team:assembly").providers_for(
            capability_key
        ) == (provider,)
