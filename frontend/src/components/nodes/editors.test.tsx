// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Timeline as MockedTimeline } from "vis-timeline/standalone";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { RunStateContext } from "../run_state_context";
import type { RunState } from "../../state/run_state";
import { ArtifactEditor, CharacterEditor, InputTraceEditor, MetaEditor } from "./editors";
import { SimulationEditor } from "./run";
import type { TraceEventItem } from "./traceModel";

vi.mock("vis-timeline/standalone", () => {
  class FakeTimeline {
    window = { start: new Date(0), end: new Date(6000) };
    options: Record<string, unknown>;
    handlers: Record<string, Array<(properties?: unknown) => void>> = {};
    items: unknown[];

    constructor(
      public container: HTMLElement,
      items: unknown[],
      options: Record<string, unknown>,
    ) {
      this.items = items;
      this.options = options;
    }

    on(event: string, handler: (properties?: unknown) => void) {
      (this.handlers[event] ??= []).push(handler);
    }

    setWindow(start: Date, end: Date) {
      this.window = { start: new Date(start), end: new Date(end) };
    }

    getWindow() {
      return this.window;
    }

    setOptions(options: Record<string, unknown>) {
      Object.assign(this.options, options);
    }

    setItems(items: unknown[]) {
      this.items = items;
    }

    destroy() {}
  }

  return { Timeline: FakeTimeline };
});

function characterNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "node-1",
    kind: "character",
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: {
      slot: 1,
      asset: "",
      level: 90,
      constellation: 0,
      talents: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
    },
    ...overrides,
  };
}

function inputTraceNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "trace-node",
    kind: "input_trace",
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: { items: [] },
    ...overrides,
  };
}

function artifactNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "artifact-node",
    kind: "artifact",
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: { slot: 1, sets: [{ asset_key: "", pieces: 4 }], stats: {} },
    ...overrides,
  };
}

function ArtifactHarness({
  node,
  onChange,
}: {
  node: WorkflowNode;
  onChange?: (params: Record<string, unknown>) => void;
}) {
  const [current, setCurrent] = useState(node);
  return (
    <ArtifactEditor
      node={current}
      onChange={(params) => {
        onChange?.(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

afterEach(cleanup);

describe("固定路径节点的编辑器", () => {
  it("角色编辑器不提供路径编辑入口", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    expect(screen.queryByText("目标路径")).toBeNull();
    expect(screen.queryByText("高级")).toBeNull();
  });

  it("角色编辑器槽位显示数字并进入滑块编辑", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    const slot = screen.getByLabelText("槽位");
    expect(slot.tagName).toBe("BUTTON");
    expect(slot.textContent).toBe("1");
    fireEvent.click(slot);
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("type")).toBe("range");
    expect(slider.getAttribute("min")).toBe("0");
    expect(slider.getAttribute("max")).toBe("3");
  });

  it("角色编辑器等级滑块覆盖 1-90 与 95、100", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("等级"));
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("max")).toBe("91");
  });

  it("角色编辑器提供三项天赋并提交修改", () => {
    const onChange = vi.fn();
    render(<CharacterEditor node={characterNode()} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("元素爆发"));
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "8" } });
    fireEvent.blur(slider);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        talents: expect.objectContaining({ elemental_burst: 9 }),
      }),
    );
  });

  it("圣遗物编辑器槽位与角色一致使用 1–4 滑块", () => {
    render(<ArtifactEditor node={artifactNode()} onChange={vi.fn()} />);
    const slot = screen.getByLabelText("槽位");
    expect(slot.tagName).toBe("BUTTON");
    expect(slot.textContent).toBe("1");
    fireEvent.click(slot);
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("type")).toBe("range");
    expect(slider.getAttribute("max")).toBe("3");
  });

  it("圣遗物件数用 1/2/4 分段按钮提交修改", () => {
    const onChange = vi.fn();
    render(<ArtifactEditor node={artifactNode()} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "1件" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        sets: [expect.objectContaining({ asset_key: "", pieces: 1 })],
      }),
    );
  });

  it("圣遗物编辑器默认一条套装，可添加、删除到空并重新添加", () => {
    const { container } = render(<ArtifactHarness node={artifactNode()} />);
    expect(screen.getByLabelText("套装 1")).toBeTruthy();
    expect(screen.queryByLabelText("套装 2")).toBeNull();
    expect(container.querySelectorAll(".artifact-set-remove")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "+ 添加套装" }));
    expect(screen.getByLabelText("套装 2")).toBeTruthy();
    expect(container.querySelectorAll(".artifact-set-remove")).toHaveLength(2);

    fireEvent.click(screen.getByTitle("删除套装 2"));
    expect(screen.queryByLabelText("套装 2")).toBeNull();
    expect(container.querySelectorAll(".artifact-set-remove")).toHaveLength(1);

    fireEvent.click(screen.getByTitle("删除套装 1"));
    expect(screen.queryByLabelText("套装 1")).toBeNull();
    expect(screen.getByRole("button", { name: "+ 添加套装" })).toBeTruthy();
  });

  it("圣遗物编辑器添加词条行：百分比按百分比输入并提交小数", () => {
    const onChange = vi.fn();
    render(
      <ArtifactHarness
        node={artifactNode({ params: { slot: 1, sets: [], stats: {} } })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "+ 添加词条" }));
    fireEvent.change(screen.getByLabelText("选择要添加的词条"), {
      target: { value: "crit_rate" },
    });

    const valueButton = screen.getByLabelText("暴击率");
    expect(valueButton.textContent).toBe("0%");
    fireEvent.click(valueButton);
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "31.1" } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ stats: { crit_rate: 0.311 } }),
    );
  });

  it("圣遗物编辑器元素精通按原值输入不做百分比换算", () => {
    const onChange = vi.fn();
    render(
      <ArtifactHarness
        node={artifactNode({
          params: { slot: 1, sets: [], stats: { elemental_mastery: 80 } },
        })}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("元素精通").textContent).toBe("80");
    fireEvent.click(screen.getByLabelText("元素精通"));
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "100" } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ stats: { elemental_mastery: 100 } }),
    );
  });

  it("圣遗物编辑器已选词条不再出现在添加选项中，可删除词条行", () => {
    render(
      <ArtifactHarness
        node={artifactNode({
          params: { slot: 1, sets: [], stats: { crit_rate: 0.311 } },
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "+ 添加词条" }));
    const addSelect = screen.getByLabelText("选择要添加的词条") as HTMLSelectElement;
    expect(Array.from(addSelect.options).some((option) => option.value === "crit_rate")).toBe(
      false,
    );
    fireEvent.blur(addSelect);

    fireEvent.click(screen.getByTitle("删除词条 暴击率"));
    expect(screen.queryByLabelText("暴击率")).toBeNull();
    expect(screen.getByRole("button", { name: "+ 添加词条" })).toBeTruthy();
  });

  it("圣遗物编辑器不提供路径编辑", () => {
    render(<ArtifactEditor node={artifactNode()} onChange={vi.fn()} />);
    expect(screen.queryByText("目标路径")).toBeNull();
    expect(screen.queryByText("高级")).toBeNull();
  });

  it("元信息编辑器提供名称与描述配置", () => {
    const onChange = vi.fn();
    render(
      <MetaEditor
        node={characterNode({ kind: "meta" })}
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("名称")).toBeTruthy();
    expect(screen.getByLabelText("描述")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "深渊满星队" },
    });
    fireEvent.blur(screen.getByLabelText("名称"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ name: "深渊满星队" }));
    expect(screen.queryByText("目标路径")).toBeNull();
    expect(screen.queryByText("高级")).toBeNull();
  });
});

describe("按键轨迹编辑器", () => {
  const traceRect = {
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 640,
    bottom: 200,
    width: 640,
    height: 200,
    toJSON: () => ({}),
  } as DOMRect;

  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(traceRect);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function TraceStateHarness() {
    const [current, setCurrent] = useState(inputTraceNode());
    return (
      <InputTraceEditor
        node={current}
        onChange={(params) => setCurrent({ ...current, params })}
      />
    );
  }

  function dragPaletteTo(
    container: HTMLElement,
    cap: string,
    clientX: number,
    clientY = 100,
  ) {
    const chip = Array.from(container.querySelectorAll(".trace-palette-chip")).find(
      (item) => item.textContent?.trim() === cap,
    ) as HTMLElement;
    expect(chip).toBeTruthy();
    fireEvent.pointerDown(chip, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(chip, { clientX, clientY });
    fireEvent.pointerUp(chip, { clientX, clientY });
  }

  it("不提供 JSON 编辑入口", () => {
    render(<InputTraceEditor node={inputTraceNode()} onChange={vi.fn()} />);
    expect(screen.queryByText("JSON 高级编辑")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("拖拽按键到时间轴创建点按块", () => {
    const onChange = vi.fn();
    const { container } = render(
      <InputTraceEditor node={inputTraceNode()} onChange={onChange} />,
    );
    dragPaletteTo(container, "E", 96);

    expect(onChange).toHaveBeenCalledTimes(1);
    const params = onChange.mock.calls[0][0] as { items: TraceEventItem[] };
    expect(params.items).toHaveLength(2);
    expect(params.items[0].events[0]).toEqual({ key: "keyboard.e", phase: "press" });
    expect(params.items[1].events[0]).toEqual({ key: "keyboard.e", phase: "release" });
    expect(params.items[1].frame - params.items[0].frame).toBe(15);
  });

  it("拖拽时幽灵块跟随指针", () => {
    const { container } = render(<InputTraceEditor node={inputTraceNode()} onChange={vi.fn()} />);
    const chip = Array.from(container.querySelectorAll(".trace-palette-chip")).find(
      (item) => item.textContent?.trim() === "E",
    ) as HTMLElement;
    expect(chip).toBeTruthy();

    fireEvent.pointerDown(chip, { button: 0, clientX: 123, clientY: 80 });
    const ghost = container.querySelector(".trace-drag-ghost") as HTMLElement;
    expect(ghost).not.toBeNull();
    const firstLeft = parseFloat(ghost.style.left);
    expect(firstLeft).toBeGreaterThan(0);

    fireEvent.pointerMove(chip, { clientX: 260, clientY: 80 });
    expect(parseFloat(ghost.style.left)).toBeGreaterThan(firstLeft);
    fireEvent.pointerUp(chip, { clientX: 260, clientY: 80 });
  });

  it("不同按键可在同一时刻创建", () => {
    const { container } = render(<TraceStateHarness />);
    dragPaletteTo(container, "E", 96);
    dragPaletteTo(container, "左键", 96);

    expect(container.querySelector(".trace-summary")?.textContent).toContain("2 个操作");
  });

  it("同一按键在同一时刻不会重复创建", () => {
    const { container } = render(<TraceStateHarness />);
    dragPaletteTo(container, "E", 96);
    dragPaletteTo(container, "E", 96);

    expect(container.querySelector(".trace-summary")?.textContent).toContain("1 个操作");
  });

  it("同键冲突时幽灵块显示阻塞状态", () => {
    const { container } = render(<TraceStateHarness />);
    dragPaletteTo(container, "E", 96);

    const chip = Array.from(container.querySelectorAll(".trace-palette-chip")).find(
      (item) => item.textContent?.trim() === "E",
    ) as HTMLElement;
    fireEvent.pointerDown(chip, { button: 0, clientX: 96, clientY: 100 });
    const ghost = container.querySelector(".trace-drag-ghost") as HTMLElement;
    expect(ghost?.className).toContain("trace-drag-ghost-blocked");
    fireEvent.pointerUp(chip, { clientX: 96, clientY: 100 });
    expect(container.querySelector(".trace-summary")?.textContent).toContain("1 个操作");
  });

  it("拖出时间轴不创建块", () => {
    const onChange = vi.fn();
    const { container } = render(
      <InputTraceEditor node={inputTraceNode()} onChange={onChange} />,
    );
    dragPaletteTo(container, "E", 96, 300);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("标记不支持的按键", () => {
    render(
      <InputTraceEditor
        node={inputTraceNode({
          params: {
            items: [{ frame: 6, events: [{ key: "keyboard.w", phase: "press" }] }],
          },
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("1 个不支持按键")).toBeTruthy();
  });

  it("未闭合按键显示警告", () => {
    const { container } = render(
      <InputTraceEditor
        node={inputTraceNode({
          params: {
            items: [{ frame: 6, events: [{ key: "keyboard.e", phase: "press" }] }],
          },
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("1 个未闭合按键")).toBeTruthy();
    expect(container.querySelector(".trace-summary")?.textContent).toContain("1 个操作");
  });

  it("编辑块后保持当前时间窗口", () => {
    const setWindowSpy = vi.spyOn(MockedTimeline.prototype, "setWindow");
    function EditingHarness() {
      const [current, setCurrent] = useState(
        inputTraceNode({
          params: {
            items: [
              { frame: 60, events: [{ key: "keyboard.e", phase: "press" }] },
              { frame: 75, events: [{ key: "keyboard.e", phase: "release" }] },
            ],
          },
        }),
      );
      return (
        <>
          <InputTraceEditor
            node={current}
            onChange={(params) => setCurrent({ ...current, params })}
          />
          <button
            type="button"
            onClick={() =>
              setCurrent({
                ...current,
                params: {
                  items: [
                    { frame: 300, events: [{ key: "keyboard.e", phase: "press" }] },
                    { frame: 315, events: [{ key: "keyboard.e", phase: "release" }] },
                  ],
                },
              })
            }
          >
            移动到 300 帧
          </button>
        </>
      );
    }

    const { getByText } = render(<EditingHarness />);
    expect(setWindowSpy).toHaveBeenCalledTimes(1);
    fireEvent.click(getByText("移动到 300 帧"));
    expect(setWindowSpy).toHaveBeenCalledTimes(1);
  });
});

describe("模拟节点编辑器：模拟入口 + 批次监控（决策 2.38 修订）", () => {
  function simulationNode(): WorkflowNode {
    return { id: "sim-1", kind: "simulation", region_id: null, position: { x: 0, y: 0 }, params: {} };
  }

  function member(
    itemId: string,
    state: "completed" | "failed" | "cancelled" | "running" | "queued",
    overrides: Partial<{ error_code: string | null; error_message: string | null }> = {},
  ) {
    return {
      item_id: itemId,
      state,
      session_id: state === "completed" ? `s-${itemId}` : null,
      error_code: null,
      error_message: null,
      created_at: "2026-08-23T10:00:00+00:00",
      ...overrides,
    };
  }

  function runStateWithBatch(status: "completed" | "running" = "completed"): RunState {
    return {
      run: {
        phase: status === "completed" ? "completed" : "simulating",
        build: [],
        buildErrors: [],
        batches: [
          {
            nodeId: "sim-1",
            name: "主配置",
            sourceRegionIds: ["region-1"],
            status,
            runId: "run-1",
            state: status,
            cancelRequested: false,
            members:
              status === "completed"
                ? [
                    member("a", "completed"),
                    member("b", "failed", {
                      error_code: "SIMULATION_FAILED",
                      error_message: "第 120 帧断言失败",
                    }),
                    member("c", "cancelled"),
                  ]
                : [
                    member("a", "running"),
                    member("b", "failed", {
                      error_code: "SIMULATION_FAILED",
                      error_message: "第 120 帧断言失败",
                    }),
                    member("c", "queued"),
                  ],
            error: null,
          },
        ],
      },
    };
  }

  function renderSimulationEditor(
    state: RunState,
    handlers: {
      onCancelBatch?: (nodeId: string) => void;
    } = {},
  ) {
    return render(
      <RunStateContext.Provider
        value={{
          runState: state,
          onCancelRun: vi.fn(),
          onCancelBatch: handlers.onCancelBatch ?? vi.fn(),
        }}
      >
        <SimulationEditor node={simulationNode()} onChange={vi.fn()} />
      </RunStateContext.Provider>,
    );
  }

  it("批次进度以分段进度条与聚合计数呈现", () => {
    const { container } = renderSimulationEditor(runStateWithBatch());
    expect(screen.getByText("完成 1/3 · 失败 1 · 已取消 1")).not.toBeNull();
    const bar = screen.getByRole("progressbar", { name: "批次成员进度" });
    expect(bar.getAttribute("aria-valuenow")).toBe("3");
    expect(bar.getAttribute("aria-valuemax")).toBe("3");
    const segments = container.querySelectorAll(".batch-progress-segment");
    expect(segments.length).toBe(3);
    expect(container.querySelector(".batch-progress-segment.seg-completed")).not.toBeNull();
    expect(container.querySelector(".batch-progress-segment.seg-failed")).not.toBeNull();
    expect(container.querySelector(".batch-progress-segment.seg-cancelled")).not.toBeNull();
  });

  it("不显示成员标签、跳转入口与指标数值", () => {
    const { container } = renderSimulationEditor(runStateWithBatch());
    expect(screen.queryByText("芭芭拉 · 等级 1")).toBeNull();
    // 完成态下唯一按钮是并发度输入本身：既无成员跳转入口，也无取消按钮。
    const buttons = container.querySelectorAll("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]?.className).toContain("number-display");
    expect(screen.queryByText(/DPS/)).toBeNull();
    expect(screen.queryByText(/总伤/)).toBeNull();
  });

  it("失败成员行直接显示错误文本", () => {
    renderSimulationEditor(runStateWithBatch("running"));
    expect(screen.getByText("完成 0/3 · 失败 1 · 运行中 1 · 排队 1")).not.toBeNull();
    expect(screen.getByText("第 120 帧断言失败")).not.toBeNull();
  });

  it("运行中的批次可取消本批，且只针对本节点", () => {
    const onCancelBatch = vi.fn();
    renderSimulationEditor(runStateWithBatch("running"), { onCancelBatch });
    fireEvent.click(screen.getByRole("button", { name: "取消本批" }));
    expect(onCancelBatch).toHaveBeenCalledWith("sim-1");
  });

  it("已完成的批次不显示取消按钮", () => {
    renderSimulationEditor(runStateWithBatch());
    expect(screen.queryByRole("button", { name: "取消本批" })).toBeNull();
  });

  it("校验通过批次不展示模拟进度，标记未提交模拟", () => {
    const state: RunState = {
      run: {
        phase: "validated",
        build: [],
        buildErrors: [],
        batches: [
          {
            nodeId: "sim-1",
            name: "主配置",
            sourceRegionIds: ["region-1"],
            status: "validated",
            runId: null,
            state: null,
            cancelRequested: false,
            members: [member("a", "queued")],
            error: null,
          },
        ],
      },
    };
    const { container } = renderSimulationEditor(state);
    expect(screen.getByText("校验通过")).not.toBeNull();
    expect(screen.getByText("未提交模拟")).not.toBeNull();
    expect(screen.queryByRole("progressbar", { name: "批次成员进度" })).toBeNull();
    expect(container.querySelector(".batch-progress")).toBeNull();
  });
});
