// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { CharacterEditor, InputTraceEditor, MetaEditor } from "./editors";

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

function TraceHarness({ node }: { node: WorkflowNode }) {
  const [current, setCurrent] = useState(node);
  return (
    <InputTraceEditor
      node={current}
      onChange={(params) => setCurrent({ ...current, params })}
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
