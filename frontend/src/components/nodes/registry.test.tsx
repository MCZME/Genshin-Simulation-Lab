import { describe, expect, it } from "vitest";

import { COLORS } from "../../theme/tokens";
import { REGISTRY } from "../../workflow/registry";
import { nodeCategoryOf, nodeKindColor } from "./registry";

describe("节点类别配色", () => {
  it("所有已注册节点都有类别色", () => {
    for (const kind of Object.keys(REGISTRY)) {
      expect(nodeCategoryOf(kind)).not.toBeNull();
    }
  });

  it("同类节点共享颜色，类别之间颜色不同", () => {
    const groups = [
      ["root", "meta", "run_options"],
      ["character", "weapon", "artifact"],
      ["enum", "range"],
      ["data_provider", "fetch"],
      ["filter", "project", "sort", "aggregate", "limit", "join", "compute"],
      ["table_config", "pie_config", "bar_config"],
      ["member_table", "pie", "bar"],
    ];
    const seen = new Set<string>();
    for (const group of groups) {
      const color = nodeKindColor(group[0]);
      for (const kind of group) {
        expect(nodeKindColor(kind)).toBe(color);
      }
      expect(seen.has(color)).toBe(false);
      seen.add(color);
    }
    expect(nodeKindColor("target")).toBe(COLORS.nodeCategory.targetConfig);
    expect(nodeKindColor("input_trace")).toBe(COLORS.nodeCategory.inputSequence);
    expect(nodeKindColor("simulation")).toBe(COLORS.nodeCategory.simulation);
  });

  it("区域对象使用区域色而非节点类别色", () => {
    expect(nodeKindColor("region")).toBe(COLORS.region.configuration);
    expect(nodeKindColor("analysis_region")).toBe(COLORS.region.analysis);
  });
});
