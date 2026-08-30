// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EventDetailResponse } from "../../api/client";
import { DamageSheet } from "./damage_sheet";

afterEach(() => {
  cleanup();
});

/** 与后端 DamageResult.to_dict()/to_audit_dict() 字段一致的最小样例。 */
const CRIT_GENERAL_EVENT = {
  session_id: "sess-1",
  ordinal: 142,
  frame: 318,
  event_type: "DAMAGE_RESOLVED",
  data: {},
  damage: {
    summary: {
      request_id: "req-142",
      frame: 318,
      damage_type: "general",
      source_ref: "character:slot_1",
      target_ref: "target:target_1",
      element: "pyro",
      damage_name: "重击",
      base_damage: 12514.0,
      damage_bonus_multiplier: 1.586,
      crit_outcome: "critical",
      crit_rate: 0.624,
      crit_damage: 1.962,
      crit_multiplier: 1.962,
      reaction_multiplier: 2.0,
      reaction: null,
      secondary_amplifying_reaction: null,
      catalyze_reaction: null,
      lunar_reaction: null,
      defense_multiplier: 0.513,
      resistance_multiplier: 0.9,
      final_multiplier: 1.0,
      official_damage: 48213.0,
      debug_multiplier: 1.0,
      final_damage: 48213.0,
    },
    audit: {
      component_results: [
        {
          component_key: "attack.main",
          attribute_key: "stat.atk.total",
          attribute_value: 2136.0,
          original_coefficient: 1.98,
          final_coefficient: 2.156,
          damage: 4605.2,
        },
      ],
      base_damage_additions: [],
      damage_bonus: { element_bonus: 0.462, modifier_bonus: 0.124, multiplier: 1.586 },
      critical: {
        can_crit: true,
        crit_rate: 0.624,
        effective_crit_rate: 0.0,
        crit_damage: 1.962,
        outcome: "critical",
        multiplier: 1.962,
      },
      defense: {
        source_level: 90,
        target_level: 90,
        defense_reduction: 0.0,
        defense_ignore: 0.0,
        multiplier: 0.513,
      },
      resistance: { resistance: 0.1, multiplier: 0.9 },
      reaction: null,
      applied_terms: [
        {
          stage: "damage_bonus_add",
          value: 0.124,
          provider_key: "buff.pyro_up",
          provider_display_name: "芭芭拉 C2 环",
        },
        {
          stage: "crit_damage_add",
          value: 0.5,
          provider_key: "artifact.crit_dmg",
        },
      ],
      rejected_terms: [
        {
          stage: "damage_bonus_add",
          value: 0.3,
          provider_key: "buff.superseded",
        },
      ],
      source_attribute_trace: [
        {
          attribute_key: "stat.atk.total",
          final_value: 2136.0,
          base_value: 1800.0,
        },
      ],
      target_attribute_trace: [],
      trace_metadata: {},
    },
  },
  entities: {
    characters: [{ slot: 1, asset_key: "character:10000014", name: "芭芭拉" }],
    targets: [{ id: "target_1", label: "试炼桩" }],
  },
} as unknown as EventDetailResponse;

const TRANSFORMATIVE_EVENT = {
  session_id: "sess-1",
  ordinal: 7,
  frame: 42,
  event_type: "DAMAGE_RESOLVED",
  data: {},
  damage: {
    summary: {
      request_id: "req-7",
      frame: 42,
      damage_type: "transformative_reaction",
      source_ref: "character:slot_1",
      target_ref: "target:1",
      element: "pyro",
      base_damage: 0.0,
      damage_bonus_multiplier: 1.0,
      crit_outcome: "not_applicable",
      crit_rate: 0.0,
      crit_damage: 0.0,
      crit_multiplier: 1.0,
      reaction_multiplier: 2.4,
      reaction: null,
      secondary_amplifying_reaction: null,
      catalyze_reaction: null,
      lunar_reaction: null,
      defense_multiplier: 1.0,
      resistance_multiplier: 0.9,
      final_multiplier: 1.0,
      official_damage: 2160.0,
      debug_multiplier: 1.0,
      final_damage: 2160.0,
    },
    audit: null,
  },
} as unknown as EventDetailResponse;

function clickSegment(label: string) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(label) }));
}

describe("DamageSheet", () => {
  it("渲染上下文条、乘法链段与等号后的最终伤害", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    expect(screen.getByText(/重击 #142/)).toBeDefined();
    expect(screen.getByText("火")).toBeDefined();
    expect(screen.getByText("直伤")).toBeDefined();
    expect(screen.getByText("芭芭拉 → 试炼桩")).toBeDefined();
    expect(screen.getByText("12,514")).toBeDefined();
    expect(screen.getByText("×1.586")).toBeDefined();
    expect(screen.getByText("48,213")).toBeDefined();
    expect(screen.getByText("暴击", { selector: ".damage-sheet-total-badge" })).toBeDefined();
  });

  it("默认展示基础段明细（伤害名 + 属性键中文化），点击链段切换对应内容", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    expect(screen.getByText("重击")).toBeDefined();
    expect(screen.getByText("倍率段明细 · 倍率 × (1+倍率修改) × 属性值")).toBeDefined();
    expect(
      screen.getByText(/攻击力/, { selector: ".damage-sheet-table td" }),
    ).toBeDefined();

    clickSegment("暴击");
    expect(screen.getByText("生效暴击率")).toBeDefined();
    expect(screen.getByText("62.4%")).toBeDefined();
    expect(screen.queryByText("倍率段明细 · 倍率 × (1+倍率修改) × 属性值")).toBeNull();
    clickSegment("增伤");
    expect(screen.getByText("元素伤加成")).toBeDefined();
    expect(screen.getByText("芭芭拉 C2 环 · 增伤加成")).toBeDefined();
    expect(screen.queryByText("生效暴击率")).toBeNull();
  });

  it("词条显示 provider 显示名并按阶段归属；缺失显示名回退原键", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    clickSegment("暴击");
    expect(screen.getByText(/artifact\.crit_dmg/)).toBeDefined();
    expect(screen.queryByText("芭芭拉 C2 环 · 增伤加成")).toBeNull();
    expect(screen.queryByText(/buff\.superseded/)).toBeNull();

    clickSegment("增伤");
    expect(screen.getByText("芭芭拉 C2 环 · 增伤加成")).toBeDefined();
    // 未生效词条没有显示名，回退 provider 原键。
    expect(screen.getByText(/buff\.superseded/)).toBeDefined();
  });

  it("属性追踪归入基础段详情并翻译属性键", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    expect(screen.getByText("属性追踪")).toBeDefined();
    expect(screen.getByText(/攻方 #1 · 攻击力/)).toBeDefined();
    expect(screen.queryByText(/stat\.atk\.total/)).toBeNull();
  });

  it("实体名解析回退：无名称时显示槽位与目标 id", () => {
    const event = {
      ...CRIT_GENERAL_EVENT,
      entities: {
        characters: [{ slot: 1, asset_key: "character:10000014", name: "" }],
        targets: [{ id: "target_1", label: "" }],
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    expect(screen.getByText("1 号位角色 → target_1")).toBeDefined();
  });

  it("非伤害事件给出明确提示", () => {
    const event = { ...CRIT_GENERAL_EVENT, damage: null } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    expect(screen.getByText("该事件不是伤害事件（DAMAGE_RESOLVED）")).toBeDefined();
  });

  it("不可暴击的伤害省略暴击段；审计缺失时详情回退摘要字段", () => {
    render(<DamageSheet event={TRANSFORMATIVE_EVENT} />);
    expect(screen.queryByRole("button", { name: /暴击/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /增伤/ })).toBeNull();

    clickSegment("反应");
    expect(screen.getByText("反应乘数")).toBeDefined();
    expect(
      screen.getByText("×2.400", { selector: ".damage-sheet-row-value" }),
    ).toBeDefined();
    expect(screen.getByText("无反应结算明细")).toBeDefined();

    clickSegment("抗性");
    expect(screen.getByText("合计乘数")).toBeDefined();
    expect(
      screen.getByText("×0.900", { selector: ".damage-sheet-row-value" }),
    ).toBeDefined();
  });
});
