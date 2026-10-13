// @vitest-environment jsdom
/** 区间图视图：列绑定折叠、内容尺寸估算与注册表契约。 */

import { describe, expect, it } from "vitest";

import { getNodeKindSpec } from "../../workflow/registry";
import { defaultIntervalBinding, type AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowNode } from "../../workflow/types";
import {
  buildIntervalData,
  estimateIntervalFit,
  type IntervalBinding,
} from "./intervalView";

const NO_OPTIONAL: Pick<
  IntervalBinding,
  "end" | "label" | "value" | "color" | "laneOrder"
> = {
  end: null,
  label: null,
  value: null,
  color: null,
  laneOrder: null,
};

function makeTable(
  columns: AnalysisTableResult["columns"],
  rows: unknown[][],
): AnalysisTableResult {
  return { columns, rows, truncated: false };
}

function rawText(_column: string, value: unknown): string {
  return String(value);
}

describe("区间图数据折叠", () => {
  it("按泳道分组并保留起止帧，零长区间保持零长", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
          { name: "end", type: "int" },
        ],
        [
          ["角色1", 30, 120],
          ["角色1", 60, 60],
          ["敌人", 0, 200],
        ],
      ),
      { ...NO_OPTIONAL, lane: "lane", start: "start", end: "end" },
      rawText,
    );

    expect(data?.lanes.map((lane) => lane.key)).toEqual(["角色1", "敌人"]);
    expect(data?.items.map((item) => [item.start, item.end])).toEqual([
      [30, 120],
      [60, 60],
      [0, 200],
    ]);
  });

  it("丢弃泳道为空或起始列非数值的行", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
          { name: "end", type: "int" },
        ],
        [
          ["", 10, 20],
          ["角色1", null, 20],
          ["角色1", "abc", 20],
          ["角色1", 10, 20],
        ],
      ),
      { ...NO_OPTIONAL, lane: "lane", start: "start", end: "end" },
      rawText,
    );

    expect(data?.items).toHaveLength(1);
    expect(data?.items[0]?.start).toBe(10);
  });

  it("结束列缺省时全部折叠为瞬时点", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
        ],
        [
          ["角色1", 30],
          ["敌人", 60],
        ],
      ),
      { lane: "lane", start: "start", ...NO_OPTIONAL },
      rawText,
    );

    expect(data?.items.map((item) => item.end)).toEqual([null, null]);
  });

  it("结束列存在但该行为空时按开放区间处理", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
          { name: "end", type: "int" },
        ],
        [["角色1", 30, null]],
      ),
      { ...NO_OPTIONAL, lane: "lane", start: "start", end: "end" },
      rawText,
    );

    expect(data?.items[0]?.end).toBeNull();
  });

  it("泳道顺序列决定泳道排序", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
          { name: "order", type: "int" },
        ],
        [
          ["角色2", 10, 2],
          ["角色1", 10, 1],
        ],
      ),
      { lane: "lane", start: "start", end: null, label: null, value: null, color: null, laneOrder: "order" },
      rawText,
    );

    expect(data?.lanes.map((lane) => lane.key)).toEqual(["角色1", "角色2"]);
  });

  it("着色键去重并排序", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "int" },
          { name: "color", type: "string" },
        ],
        [
          ["角色1", 10, "火"],
          ["角色1", 20, "雷"],
          ["角色2", 30, "火"],
        ],
      ),
      { lane: "lane", start: "start", end: null, label: null, value: null, color: "color", laneOrder: null },
      rawText,
    );

    expect(data?.colorKeys).toEqual(["火", "雷"]);
  });

  it("必填列不在上游表中时返回 null", () => {
    const data = buildIntervalData(
      makeTable([{ name: "start", type: "int" }], [[10]]),
      { lane: "lane", start: "start", ...NO_OPTIONAL },
      rawText,
    );

    expect(data).toBeNull();
  });

  it("起始列非数值列时返回 null", () => {
    const data = buildIntervalData(
      makeTable(
        [
          { name: "lane", type: "string" },
          { name: "start", type: "string" },
        ],
        [["角色1", "10"]],
      ),
      { lane: "lane", start: "start", ...NO_OPTIONAL },
      rawText,
    );

    expect(data).toBeNull();
  });
});

describe("区间图内容尺寸估算", () => {
  const LANE_COUNT = 12;

  function lanesWith(end: number[]): AnalysisTableResult["rows"] {
    const rows: AnalysisTableResult["rows"] = [];
    for (let index = 0; index < LANE_COUNT; index += 1) {
      rows.push([`角色${index}`, end[0], end[1]]);
      rows.push([`角色${index}`, end[2], end[3]]);
    }
    return rows;
  }

  it("同泳道并发区间按堆叠层数抬高内容高", () => {
    const columns = [
      { name: "lane", type: "string" },
      { name: "start", type: "int" },
      { name: "end", type: "int" },
    ];
    const binding: IntervalBinding = {
      lane: "lane",
      start: "start",
      end: "end",
      label: null,
      value: null,
      color: null,
      laneOrder: null,
    };
    const flat = buildIntervalData(
      makeTable(columns, lanesWith([0, 10, 20, 30])),
      binding,
      rawText,
    );
    const stacked = buildIntervalData(
      makeTable(columns, lanesWith([0, 100, 50, 150])),
      binding,
      rawText,
    );

    const flatFit = estimateIntervalFit(flat);
    const stackedFit = estimateIntervalFit(stacked);
    expect(flatFit.fitHeight).not.toBeNull();
    expect(stackedFit.fitHeight).not.toBeNull();
    expect(stackedFit.fitHeight ?? 0).toBeGreaterThan(flatFit.fitHeight ?? 0);
  });

  it("无数据时高度不可估算", () => {
    expect(estimateIntervalFit(null).fitHeight).toBeNull();
  });
});

describe("区间图默认绑定", () => {
  it("取第一个字符串列作泳道、前两个数值列作起止帧", () => {
    const binding = defaultIntervalBinding([
      { name: "frame", type: "int" },
      { name: "lane", type: "string" },
      { name: "start", type: "int" },
    ]);

    expect(binding).toEqual({ lane: "lane", start: "frame", end: "start" });
  });

  it("没有数值列时无法推导绑定", () => {
    expect(defaultIntervalBinding([{ name: "lane", type: "string" }])).toBeNull();
  });
});

describe("区间图节点注册表", () => {
  it("视图消费 table 且一期无输出端口", () => {
    const spec = getNodeKindSpec("interval");
    expect(spec?.region).toBe("analysis");
    expect(spec?.ports.inputs[0]!.dataLanguage).toBe("table");
    expect(spec?.ports.outputs).toHaveLength(0);
  });

  it("配置节点要求泳道列与起始列，其余为可选", () => {
    const spec = getNodeKindSpec("interval_config");
    expect(spec?.paramFields.lane?.required).toBe(true);
    expect(spec?.paramFields.start?.required).toBe(true);
    expect(spec?.paramFields.end?.required).toBeUndefined();

    const node: WorkflowNode = {
      id: "c1",
      kind: "interval_config",
      region_id: "a1",
      position: { x: 0, y: 0 },
      params: {},
    };
    expect(spec?.validate(node).length).toBeGreaterThan(0);
    expect(spec?.validate({ ...node, params: { lane: "l", start: "s" } })).toEqual([]);
  });
});
