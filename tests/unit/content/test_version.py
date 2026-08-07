from __future__ import annotations

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.content import (
    VERSION as BARBARA_VERSION,
)
from genshin_sim.content.characters.mondstadt.barbara.content import (
    create_barbara_content_unit,
)
from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.testing.runtime_probe.content import (
    VERSION as RUNTIME_PROBE_VERSION,
)
from genshin_sim.content.characters.testing.runtime_probe.content import (
    create_runtime_probe_content_unit,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest


def test_content_unit_requires_non_empty_version():
    try:
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="",
            slot=1,
        )
    except ValueError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("ContentUnit 应拒绝空 version")


def test_barbara_content_unit_exposes_version():
    unit = create_barbara_content_unit(
        CharacterContentUnitRequest(
            handler_key=BARBARA_CHARACTER_HANDLER_KEY,
            character_key="character:10000014",
            slot=1,
        )
    )
    assert BARBARA_VERSION == "dev-action"
    assert unit.version == BARBARA_VERSION


def test_runtime_probe_content_unit_exposes_version():
    unit = create_runtime_probe_content_unit(
        CharacterContentUnitRequest(
            handler_key=RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            character_key="character:test_character",
            slot=1,
        )
    )
    assert RUNTIME_PROBE_VERSION == "dev-runtime-probe"
    assert unit.version == RUNTIME_PROBE_VERSION
