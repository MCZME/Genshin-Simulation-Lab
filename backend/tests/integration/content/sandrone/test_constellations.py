"""桑多涅命座的纵向集成：C6 集束型额外段的组合行为。

数值全部为合成数据（助手资产库，见测试规范 §3.2）；射线帧序列由法洁欧
节奏常量推导，不复制数据真值。
"""

from __future__ import annotations

import pytest

from tests.helpers import sandrone as sandrone_helpers

RAY_DISPLAY_NAME = "重击冷凝射线伤害"
EXTRA_DISPLAY_NAME = "集束型冷凝射线伤害"


def test_c6_extra_segments_ride_each_ray_from_the_third(sandrone_assembled):
    # C6：自第 3 次发射冷凝射线起，在原本射线之上追加 1 段集束型冷凝射线
    # 伤害（普通变体 100% 攻击力），至多 4 段。1 命（C6 必带 C1）0→100 涌现
    # 6 条射线，追加段落在第 3–6 条，恰好吃满 4 段；射线本身的帧位与节奏
    # 不因追加段改变。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(444, 2, 440, constellation=6)
    )
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    names = [(e.frame, e.payload.result.damage_name) for e in events]
    ray_frames = sandrone_helpers.charged_ray_frames(2, 6)
    assert [frame for frame, name in names if name == RAY_DISPLAY_NAME] == ray_frames
    extras = [e for e in events if e.payload.result.damage_name == EXTRA_DISPLAY_NAME]
    assert [e.frame for e in extras] == ray_frames[2:]
    atk = sandrone_helpers.resolved_atk(assembled)
    for extra in extras:
        result = extra.payload.result
        assert result.main_attack_tag == "重击"
        assert result.base_damage == pytest.approx(atk * 1.0)
