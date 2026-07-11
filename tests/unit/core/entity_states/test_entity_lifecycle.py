from __future__ import annotations

import pytest

from genshin_sim.core.entity_states import EntityLifecycle, EntityLifecycleState


def test_entity_lifecycle_tracks_active_window_and_expiration():
    lifecycle = EntityLifecycle(created_frame=10, expires_at_frame=15)

    assert not lifecycle.is_active_at(9)
    assert lifecycle.is_active_at(10)
    assert lifecycle.is_active_at(14)
    assert not lifecycle.is_active_at(15)

    lifecycle.expire()

    assert lifecycle.state is EntityLifecycleState.EXPIRED
    assert not lifecycle.is_active_at(12)


def test_entity_lifecycle_valid_case_smoke():
    lifecycle = EntityLifecycle(created_frame=0, expires_at_frame=1)

    assert lifecycle.is_active_at(0)


def test_entity_lifecycle_rejects_negative_created_frame():
    with pytest.raises(ValueError, match="实体创建帧不能为负数"):
        EntityLifecycle(created_frame=-1)


def test_entity_lifecycle_rejects_expiration_before_or_at_creation():
    with pytest.raises(ValueError, match="实体过期帧必须晚于创建帧"):
        EntityLifecycle(created_frame=10, expires_at_frame=10)
