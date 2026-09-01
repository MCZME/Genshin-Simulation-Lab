// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NodeProps } from "@xyflow/react";
import type { NodeSize, WorkflowNode } from "../../workflow/types";
import { NodeCard, type WorkflowNodeData } from "./NodeCard";

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    Handle: () => null,
    useReactFlow: () => ({
      screenToFlowPosition: (point: { x: number; y: number }) => ({
        x: point.x,
        y: point.y,
      }),
    }),
  };
});

vi.mock("vis-timeline/standalone", () => {
  class FakeTimeline {
    window = { start: new Date(0), end: new Date(6000) };
    options: Record<string, unknown>;

    constructor(
      public container: HTMLElement,
      public items: unknown[],
      options: Record<string, unknown>,
    ) {
      this.options = options;
    }

    on() {}

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

function renderNodeCard(
  node: WorkflowNode,
  onResizeNode: (nodeId: string, size: NodeSize) => void = vi.fn(),
) {
  const data: WorkflowNodeData = {
    node,
    definition: {
      schema_version: 1,
      meta: { name: "测试" },
      regions: [],
      nodes: [node],
      edges: [],
      layout: {},
    },
    onParamsChange: vi.fn(),
    onDeleteNode: vi.fn(),
    onLocateNode: vi.fn(),
    onMoveEdgeOrder: vi.fn(),
    incomingGroups: [],
    memberPorts: [],
    groupCount: 0,
    diagnostics: [],
    dimmed: false,
    stepRunning: false,
    interactionLocked: false,
    onResizeNode,
    onResizeNodeWithFixedWidth: vi.fn(),
  };
  const props = { id: node.id, data, selected: false } as unknown as NodeProps;
  return render(<NodeCard {...props} />);
}

function traceNode(size?: NodeSize): WorkflowNode {
  return {
    id: "trace-1",
    kind: "input_trace",
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: { items: [] },
    ...(size === undefined ? {} : { size }),
  };
}

beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
    configurable: true,
    value: vi.fn(),
  });
  Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
    configurable: true,
    value: vi.fn(() => false),
  });
  Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", {
    configurable: true,
    value: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
});

describe("NodeCard 按键轨迹节点宽度手柄", () => {
  it("渲染右侧宽度手柄并使用默认宽度", () => {
    const { container } = renderNodeCard(traceNode());
    expect(container.querySelector(".node-resize-handle-right")).not.toBeNull();
    expect((container.querySelector(".node-card") as HTMLElement).style.width).toBe("720px");
  });

  it("已保存的宽度被采用", () => {
    const { container } = renderNodeCard(traceNode({ width: 900, height: 300 }));
    expect((container.querySelector(".node-card") as HTMLElement).style.width).toBe("900px");
  });

  it("拖拽手柄提交宽度并夹持在上下限内", () => {
    const onResizeNode = vi.fn();
    const { container } = renderNodeCard(traceNode(), onResizeNode);
    const handle = container.querySelector(".node-resize-handle-right") as HTMLElement;

    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(handle, { clientX: 200, clientY: 0 });
    fireEvent.pointerUp(handle, { clientX: 200, clientY: 0 });
    expect(onResizeNode).toHaveBeenCalledWith("trace-1", { width: 920, height: 360 });

    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(handle, { clientX: -2000, clientY: 0 });
    fireEvent.pointerUp(handle, { clientX: -2000, clientY: 0 });
    expect(onResizeNode).toHaveBeenLastCalledWith("trace-1", { width: 560, height: 360 });
  });
});
