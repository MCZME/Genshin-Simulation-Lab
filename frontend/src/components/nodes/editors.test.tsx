// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { RunStateContext } from "../run_state_context";
import type { RunState } from "../../state/run_state";
import { ArtifactEditor, CharacterEditor, InputTraceEditor, MetaEditor } from "./editors";
import { SimulationEditor } from "./run";

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

function TraceHarness({ node }: { node: WorkflowNode }) {
  const [current, setCurrent] = useState(node);
  return (
    <InputTraceEditor
      node={current}
      onChange={(params) => setCurrent({ ...current, params })}
    />
  );
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
  function mockTimelineRect(container: HTMLElement) {
    const timeline = container.querySelector(".trace-timeline") as HTMLElement;
    expect(timeline).not.toBeNull();
    const width = parseFloat(timeline.style.width);
    vi.spyOn(timeline, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: width,
      bottom: 120,
      width,
      height: 120,
      toJSON: () => ({}),
    } as DOMRect);
  }

  function dragPaletteTo(
    container: HTMLElement,
    cap: string,
    clientX: number,
    clientY = 60,
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
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    const block = container.querySelector(".trace-block");
    expect(block).not.toBeNull();
    expect((block as HTMLElement).style.left).toBe("96px");
    expect(block!.textContent).toContain("E");
    expect((block as HTMLElement).style.getPropertyValue("--key-color")).toBe("#3b82f6");
  });

  it("拖拽时幽灵块显示实际插入位置", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);
    const chip = Array.from(container.querySelectorAll(".trace-palette-chip")).find(
      (item) => item.textContent?.trim() === "E",
    ) as HTMLElement;
    expect(chip).toBeTruthy();

    fireEvent.pointerDown(chip, { button: 0, clientX: 123, clientY: 45 });
    const ghost = container.querySelector(".trace-drag-ghost") as HTMLElement;
    expect(ghost).not.toBeNull();
    expect(ghost.style.left).toBe("123.2px");
    expect(ghost.style.top).toBe("23px");
    expect(ghost.style.width).toBe("24px");

    fireEvent.pointerMove(chip, { clientX: 260, clientY: 90 });
    expect(ghost.style.left).toBe("260.8px");
    expect(ghost.style.top).toBe("23px");

    fireEvent.pointerUp(chip, { clientX: 260, clientY: 90 });
  });

  it("同一时刻的两个按键自动分到不同轨道", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    dragPaletteTo(container, "左键", 96);

    const blocks = container.querySelectorAll(".trace-block");
    expect(blocks.length).toBe(2);
    const tops = new Set(Array.from(blocks, (block) => (block as HTMLElement).style.top));
    expect(tops.size).toBe(2);
  });

  it("同一按键在同一时刻不会重复创建", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    dragPaletteTo(container, "E", 96);

    expect(container.querySelectorAll(".trace-block").length).toBe(1);
  });

  it("拖动右侧把手可延长按住时长", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    let block = container.querySelector(".trace-block") as HTMLElement;
    const handle = block.querySelector(".trace-block-handle-right");

    fireEvent.pointerDown(handle!, { button: 0, clientX: 124 });
    fireEvent.pointerMove(block, { clientX: 192 });
    fireEvent.pointerUp(block, { button: 0 });

    block = container.querySelector(".trace-block") as HTMLElement;
    expect(block.style.width).toBe("92.8px");
  });

  it("拖动块后松开即落在新位置", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    let block = container.querySelector(".trace-block") as HTMLElement;

    fireEvent.pointerDown(block, { button: 0, clientX: 96, clientY: 60 });
    fireEvent.pointerMove(block, { clientX: 192, clientY: 60 });
    fireEvent.pointerUp(block, { clientX: 192, clientY: 60 });

    block = container.querySelector(".trace-block") as HTMLElement;
    expect(block.style.left).toBe("192px");
  });

  it("同键块可以拖到另一个块右侧", () => {
    const { container } = render(<TraceHarness node={inputTraceNode()} />);
    mockTimelineRect(container);

    dragPaletteTo(container, "E", 96);
    dragPaletteTo(container, "E", 288);
    let blocks = container.querySelectorAll(".trace-block");
    expect(blocks.length).toBe(2);

    fireEvent.pointerDown(blocks[0], { button: 0, clientX: 96, clientY: 60 });
    fireEvent.pointerMove(blocks[0], { clientX: 320, clientY: 60 });
    fireEvent.pointerUp(blocks[0], { clientX: 320, clientY: 60 });

    blocks = container.querySelectorAll(".trace-block");
    expect(blocks.length).toBe(2);
    const lefts = Array.from(blocks, (block) =>
      parseFloat((block as HTMLElement).style.left),
    ).sort((a, b) => a - b);
    expect(lefts).toEqual([288, 320]);
  });

  it("拖出时间轴删除事件块", () => {
    const { container } = render(
      <TraceHarness
        node={inputTraceNode({
          params: {
            items: [
              { frame: 60, events: [{ key: "keyboard.e", phase: "press" }] },
              { frame: 75, events: [{ key: "keyboard.e", phase: "release" }] },
            ],
          },
        })}
      />,
    );
    mockTimelineRect(container);
    const block = container.querySelector(".trace-block") as HTMLElement;
    expect(block).not.toBeNull();

    fireEvent.pointerDown(block, { button: 0, clientX: 96, clientY: 60 });
    fireEvent.pointerMove(block, { clientX: -50, clientY: 60 });
    const hint = document.body.querySelector(".trace-delete-ghost");
    expect(hint).not.toBeNull();
    fireEvent.pointerUp(block, { clientX: -50, clientY: 60 });

    expect(container.querySelector(".trace-block")).toBeNull();
    expect(document.body.querySelector(".trace-delete-ghost")).toBeNull();
  });

  it("标记不支持的按键", () => {
    const { container } = render(
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
    const block = container.querySelector(".trace-block");
    expect(block?.className).toContain("trace-block-unsupported");
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
