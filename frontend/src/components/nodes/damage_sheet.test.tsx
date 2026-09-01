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
      formula_key: "damage_formula.general",
      source_ref: "character:slot_1",
      target_ref: "target:target_1",
      element: "pyro",
      damage_name: "重击",
      base_damage: 12514.0,
      damage_bonus_multiplier: 1.586,
      crit_outcome: "critical",
      crit_rate: 0.624,
      crit_damage: 0.962,
      crit_multiplier: 1.962,
      reaction_multiplier: 1.0,
      reaction: null,
      secondary_amplifying_reaction: null,
      catalyze_reaction: null,
      lunar_reaction: null,
      defense_multiplier: 1.0,
      resistance_multiplier: 1.0,
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
        effective_crit_rate: 0.624,
        crit_damage: 0.962,
        outcome: "critical",
        multiplier: 1.962,
      },
      defense: {
        source_level: 90,
        target_level: 90,
        defense_reduction: 0.0,
        defense_ignore: 0.0,
        multiplier: 1.0,
      },
      resistance: { resistance: 0.0, multiplier: 1.0 },
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
        {
          stage: "panel_attribute_value",
          value: 2136.0,
          provider_key: "panel.stat.atk.total",
          component_key: "attack.main",
        },
        {
          stage: "panel_element_bonus",
          value: 0.462,
          provider_key: "panel.bonus.damage.pyro",
        },
        {
          stage: "panel_crit_rate",
          value: 0.624,
          provider_key: "panel.stat.crit_rate",
        },
        {
          stage: "panel_crit_damage",
          value: 0.462,
          provider_key: "panel.stat.crit_damage",
        },
        {
          stage: "panel_resistance",
          value: 0.0,
          provider_key: "panel.resistance.pyro",
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
      formula_key: "damage_formula.transformative_reaction",
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

/** 抗性区带 resistance_add 词条的通用伤害样例。 */
const RESISTANCE_TERM_EVENT = (() => {
  const base = CRIT_GENERAL_EVENT as unknown as {
    damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
  };
  return {
    ...CRIT_GENERAL_EVENT,
    damage: {
      ...base.damage,
      summary: { ...base.damage.summary, resistance_multiplier: 1.15 },
      audit: {
        ...base.damage.audit,
        resistance: {
          resistance: -0.15,
          base_resistance: 0.1,
          resistance_add: -0.25,
          multiplier: 1.15,
        },
        applied_terms: [
          ...(base.damage.audit.applied_terms as Record<string, unknown>[]).filter(
            (term) => term.stage !== "panel_resistance",
          ),
          {
            stage: "panel_resistance",
            value: 0.1,
            provider_key: "panel.resistance.pyro",
          },
          {
            stage: "resistance_add",
            value: -0.25,
            provider_key: "buff.reaction.superconduct.physical_resistance_reduction",
            provider_display_name: "超导 物理抗性降低",
          },
        ],
        rejected_terms: [
          ...(base.damage.audit.rejected_terms as Record<string, unknown>[]),
          {
            stage: "resistance_add",
            value: -0.1,
            provider_key: "buff.res_shred.superseded",
          },
        ],
      },
    },
  } as unknown as EventDetailResponse;
})();

function clickSegment(label: string) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(label) }));
}

describe("DamageSheet", () => {
  it("渲染上下文条、乘法链段与等号后的最终伤害", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    // 上下文条：元素徽标 + 伤害名 + 弱化帧数 + 右对齐实体名；不再显示 ordinal。
    expect(screen.getByText("重击", { selector: ".damage-sheet-context-name" })).toBeDefined();
    expect(screen.getByText("火", { selector: ".damage-sheet-element-badge" })).toBeDefined();
    expect(screen.getByText("帧 318", { selector: ".damage-sheet-context-frame" })).toBeDefined();
    expect(screen.getByText("芭芭拉 → 试炼桩")).toBeDefined();
    expect(screen.getByText("12,514", { selector: ".damage-sheet-seg-value" })).toBeDefined();
    expect(screen.getByText("1.586", { selector: ".damage-sheet-seg-value" })).toBeDefined();
    expect(screen.getByText("48,213", { selector: ".damage-sheet-total-value" })).toBeDefined();
    expect(screen.getByText("暴击", { selector: ".damage-sheet-total-badge" })).toBeDefined();
  });

  it("基础段默认展示公式区与修饰项抽屉，点击链段切换", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    expect(screen.getByText("基础区")).toBeDefined();
    // 数值为 0 的槽位与值为 1 的括号组不显示：公式简化为 属性 × 倍率。
    expect(screen.getByText("198.0%")).toBeDefined();
    expect(screen.queryByText("0.0%")).toBeNull();
    expect(screen.queryByText(/× \(1 \+/)).toBeNull();
    // 单组件且无加值时不再重复渲染合计行：公式区只有组件贡献一个结果。
    expect(document.querySelectorAll(".damage-sheet-formula-result")).toHaveLength(1);
    clickSegment("暴击");
    expect(screen.getByText("96.2%", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(screen.getByText("面板暴击伤害")).toBeDefined();
    expect(screen.queryByText(/攻击力 2,136/)).toBeNull();
    clickSegment("增伤");
    expect(screen.getByText("元素伤害加成")).toBeDefined();
    expect(screen.getByText("芭芭拉 C2 环")).toBeDefined();
    expect(screen.queryByText("面板暴击伤害")).toBeNull();
  });

  it("词条按阶段归属槽位抽屉，显示 provider 显示名并回退原键", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    clickSegment("暴击");
    expect(screen.getByText(/artifact\.crit_dmg/)).toBeDefined();
    expect(screen.queryByText("芭芭拉 C2 环")).toBeNull();

    clickSegment("增伤");
    expect(screen.getByText("芭芭拉 C2 环")).toBeDefined();
    // 未生效词条没有显示名，回退 provider 原键并划线呈现。
    expect(screen.getByText(/buff\.superseded/)).toBeDefined();
    expect(document.querySelector(".damage-sheet-row--rejected")).not.toBeNull();
  });

  it("面板读取词条作为抽屉基础行渲染，与效果词条分开展示", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    clickSegment("增伤");
    const bonusBaseLabels = Array.from(
      document.querySelectorAll(".damage-sheet-row--base .damage-sheet-row-label"),
    ).map((el) => el.textContent);
    expect(bonusBaseLabels).toContain("元素伤害加成");
    expect(screen.getByText("+46.2%", { selector: ".damage-sheet-row-value" })).toBeDefined();

    clickSegment("暴击");
    const critBaseLabels = Array.from(
      document.querySelectorAll(".damage-sheet-row--base .damage-sheet-row-label"),
    ).map((el) => el.textContent);
    expect(critBaseLabels).toContain("面板暴击伤害");
    expect(critBaseLabels).toContain("面板暴击率");
    expect(screen.getByText("+46.2%", { selector: ".damage-sheet-row-value" })).toBeDefined();
    expect(screen.getByText("62.4%", { selector: ".damage-sheet-row-value" })).toBeDefined();
  });

  it("基础区面板属性读取渲染为倍率段属性抽屉", () => {
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    // 默认选中基础区：属性值成为可点击槽位，抽屉展示面板读取词条
    expect(screen.getByText("2,136", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(screen.getByText("倍率段属性")).toBeDefined();
    expect(screen.getByText("攻击力（attack.main）")).toBeDefined();
    expect(screen.getByText("2,136", { selector: ".damage-sheet-row-value" })).toBeDefined();
  });

  it("抗性区仅面板读取时也显示抗性调整抽屉", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.9 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: 0.1,
            base_resistance: 0.1,
            resistance_add: 0,
            multiplier: 0.9,
          },
          applied_terms: [
            ...(base.damage.audit.applied_terms as Record<string, unknown>[]).filter(
              (term) => term.stage !== "panel_resistance",
            ),
            {
              stage: "panel_resistance",
              value: 0.1,
              provider_key: "panel.resistance.pyro",
            },
          ],
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(screen.getByText("10.0%", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(screen.getByText("抗性调整")).toBeDefined();
    expect(screen.getByText("目标基础抗性")).toBeDefined();
    expect(screen.getByText("10.0%", { selector: ".damage-sheet-row-value" })).toBeDefined();
  });

  it("反应区面板精通读取渲染为元素精通抽屉", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, reaction_multiplier: 1.5 },
        audit: {
          ...base.damage.audit,
          reaction: {
            kind: "amplifying",
            occurrence_ref: "occurrence:1",
            reaction_profile_key: "reaction_profile.test",
            base_multiplier: 1.5,
            elemental_mastery: 180,
            mastery_bonus: 0.3167,
            reaction_bonus: 0,
            multiplier: 1.5,
          },
          applied_terms: [
            ...(base.damage.audit.applied_terms as Record<string, unknown>[]),
            {
              stage: "panel_elemental_mastery",
              value: 180,
              provider_key: "panel.stat.elemental_mastery",
            },
          ],
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("反应");
    expect(screen.getByText("元素精通", { selector: ".damage-sheet-drawer-title" })).toBeDefined();
    expect(screen.getByText("元素精通", { selector: ".damage-sheet-row-label" })).toBeDefined();
    expect(screen.getByText("180", { selector: ".damage-sheet-row-value" })).toBeDefined();
  });

  it("属性解析审计不在伤害详情展示", () => {
    // 后端 audit 载荷仍携带 source/target_attribute_trace，伤害详情只呈现伤害审计。
    render(<DamageSheet event={CRIT_GENERAL_EVENT} />);
    expect(screen.queryByText("属性追踪")).toBeNull();
    expect(screen.queryByText(/攻方 #1/)).toBeNull();
    expect(screen.queryByText(/守方 #/)).toBeNull();
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

  it("不可暴击的伤害省略暴击段；审计缺失时公式回退摘要数值", () => {
    render(<DamageSheet event={TRANSFORMATIVE_EVENT} />);
    expect(screen.queryByRole("button", { name: /暴击/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /增伤/ })).toBeNull();

    expect(screen.getByText("无审计数据")).toBeDefined();
    clickSegment("反应");
    expect(
      screen.getByText(/2\.400/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
    expect(screen.getByText("无反应结算明细")).toBeDefined();

    clickSegment("抗性");
    expect(
      screen.getByText(/0\.900/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
    // 无可修饰词条时不显示"无伤害词条修饰项"提示
    expect(screen.queryByText(/抗性来自目标属性/)).toBeNull();
    expect(screen.queryByText(/无伤害词条修饰项/)).toBeNull();
  });

  it("抗性区公式直接代入抗性值，不重复标注符号名", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.9 },
        audit: { ...base.damage.audit, resistance: { resistance: 0.1, multiplier: 0.9 } },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(screen.getByText("1 − 10.0%", { selector: ".damage-sheet-formula-text" })).toBeDefined();
    // 不再重复"· 抗性 +10.0%"标注；结果仍由公式得出。
    expect(screen.queryByText(/· 抗性/)).toBeNull();
    expect(screen.getByText(/0\.900/, { selector: ".damage-sheet-formula-result" })).toBeDefined();
  });

  it("抗性区负抗无词条时公式展示 1 + |R| ÷ 2，不预计算半值", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 1.15 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: -0.3,
            base_resistance: -0.3,
            resistance_add: 0,
            multiplier: 1.15,
          },
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(
      screen.getByText("1 + |-30.0%| ÷ 2", { selector: ".damage-sheet-formula-text" }),
    ).toBeDefined();
    expect(screen.queryByText("1 + 15.0%")).toBeNull();
    // 原值已在公式内，不再追加"· 抗性 -30.0%"标注
    expect(screen.queryByText(/· 抗性/)).toBeNull();
    expect(
      screen.getByText(/1\.150/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
  });

  it("抗性区高抗无词条时公式展示 1 ÷ (1 + 4×R)", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.238 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: 0.8,
            base_resistance: 0.8,
            resistance_add: 0,
            multiplier: 0.238,
          },
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(
      screen.getByText("1 ÷ (1 + 4×80.0%)", { selector: ".damage-sheet-formula-text" }),
    ).toBeDefined();
    expect(
      screen.getByText(/0\.238/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
  });

  it("抗性区边界 R = 0.75 归入普通段 1 − R", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.25 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: 0.75,
            base_resistance: 0.75,
            resistance_add: 0,
            multiplier: 0.25,
          },
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(
      screen.getByText("1 − 75.0%", { selector: ".damage-sheet-formula-text" }),
    ).toBeDefined();
    expect(
      screen.getByText(/0\.250/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
  });

  it("抗性区高抗带词条时槽位进入 1 ÷ (1 + 4×R) 骨架", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.238 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: 0.8,
            base_resistance: 0.1,
            resistance_add: 0.7,
            multiplier: 0.238,
          },
          applied_terms: [
            ...(base.damage.audit.applied_terms as Record<string, unknown>[]).filter(
              (term) => term.stage !== "panel_resistance",
            ),
            {
              stage: "panel_resistance",
              value: 0.1,
              provider_key: "panel.resistance.pyro",
            },
            {
              stage: "resistance_add",
              value: 0.7,
              provider_key: "buff.res_up",
              provider_display_name: "抗性提升",
            },
          ],
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(screen.getByText("1 ÷ (1 + 4×")).toBeDefined();
    expect(screen.getByText("80.0%", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(screen.getByText(")")).toBeDefined();
    expect(
      screen.getByText(/0\.238/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
    expect(screen.getByText("+80.0%", { selector: ".damage-sheet-drawer-total" })).toBeDefined();
  });

  it("抗性区展示 resistance_add 词条：负抗时槽位显示有效抗性并嵌入分段公式", () => {
    render(<DamageSheet event={RESISTANCE_TERM_EVENT} />);
    clickSegment("抗性");
    // 公式骨架：1 + |槽位| ÷ 2；槽位显示基础抗性与生效词条合计后的有效抗性
    expect(screen.getByText("1 + |")).toBeDefined();
    expect(screen.getByText("-15.0%", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(screen.getByText("| ÷ 2")).toBeDefined();
    expect(
      screen.getByText(/1\.150/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
    // 槽位已给出原值，不再追加"· 抗性"标注
    expect(screen.queryByText(/· 抗性/)).toBeNull();
    // 抽屉：合计等于槽位值，基础行 + 生效词条 + 未生效词条（划线）
    expect(screen.getByText("抗性调整")).toBeDefined();
    expect(screen.getByText("-15.0%", { selector: ".damage-sheet-drawer-total" })).toBeDefined();
    expect(screen.getByText("目标基础抗性")).toBeDefined();
    expect(screen.getByText("超导 物理抗性降低")).toBeDefined();
    expect(screen.getByText(/buff\.res_shred\.superseded/)).toBeDefined();
    expect(document.querySelector(".damage-sheet-row--rejected")).not.toBeNull();
    expect(screen.queryByText(/抗性来自目标属性/)).toBeNull();
  });

  it("抗性区正抗带词条时槽位直接代入公式骨架", () => {
    const base = CRIT_GENERAL_EVENT as unknown as {
      damage: { summary: Record<string, unknown>; audit: Record<string, unknown> };
    };
    const event = {
      ...CRIT_GENERAL_EVENT,
      damage: {
        ...base.damage,
        summary: { ...base.damage.summary, resistance_multiplier: 0.7 },
        audit: {
          ...base.damage.audit,
          resistance: {
            resistance: 0.3,
            base_resistance: 0.1,
            resistance_add: 0.2,
            multiplier: 0.7,
          },
          applied_terms: [
            ...(base.damage.audit.applied_terms as Record<string, unknown>[]).filter(
              (term) => term.stage !== "panel_resistance",
            ),
            {
              stage: "panel_resistance",
              value: 0.1,
              provider_key: "panel.resistance.pyro",
            },
            {
              stage: "resistance_add",
              value: 0.2,
              provider_key: "buff.res_up",
              provider_display_name: "抗性提升",
            },
          ],
        },
      },
    } as unknown as EventDetailResponse;
    render(<DamageSheet event={event} />);
    clickSegment("抗性");
    expect(screen.getByText("1 −")).toBeDefined();
    expect(screen.getByText("30.0%", { selector: ".damage-sheet-slot" })).toBeDefined();
    expect(
      screen.getByText(/0\.700/, { selector: ".damage-sheet-formula-result" }),
    ).toBeDefined();
    expect(screen.getByText("抗性调整")).toBeDefined();
    expect(screen.getByText("+30.0%", { selector: ".damage-sheet-drawer-total" })).toBeDefined();
    expect(screen.getByText("抗性提升")).toBeDefined();
    expect(screen.queryByText(/抗性来自目标属性/)).toBeNull();
  });
});
