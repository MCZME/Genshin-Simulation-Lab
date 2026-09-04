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
  onResizeNode: (nodeId: string, size: Partial<NodeSize>) => void = vi.fn(),
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

function viewNode(
  kind: "member_table" | "pie" | "bar",
  size?: NodeSize,
): WorkflowNode {
  return {
    id: `${kind}-1`,
    kind,
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params: {},
    ...(size === undefined ? {} : { size }),
  };
}

function detailNode(kind: "damage_detail" | "attribute_detail", size?: NodeSize): WorkflowNode {
  return {
    id: `${kind}-1`,
    kind,
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params: {},
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
    expect(onResizeNode).toHaveBeenCalledWith("trace-1", { width: 920 });

    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(handle, { clientX: -2000, clientY: 0 });
    fireEvent.pointerUp(handle, { clientX: -2000, clientY: 0 });
    expect(onResizeNode).toHaveBeenLastCalledWith("trace-1", { width: 560 });
  });
});

describe("NodeCard 视图节点手柄", () => {
  it("表格/饼图/柱状图均渲染宽度与高度手柄", () => {
    for (const kind of ["member_table", "pie", "bar"] as const) {
      cleanup();
      const { container } = renderNodeCard(viewNode(kind));
      expect(container.querySelector(".node-resize-handle-right")).not.toBeNull();
      expect(container.querySelector(".node-resize-handle-bottom")).not.toBeNull();
      expect((container.querySelector(".node-card") as HTMLElement).style.width).toBe(
        "560px",
      );
    }
  });

  it("视图节点拖宽按轴部分提交宽度", () => {
    const onResizeNode = vi.fn();
    const { container } = renderNodeCard(viewNode("bar"), onResizeNode);
    const handle = container.querySelector(".node-resize-handle-right") as HTMLElement;

    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(handle, { clientX: 300, clientY: 0 });
    fireEvent.pointerUp(handle, { clientX: 300, clientY: 0 });
    expect(onResizeNode).toHaveBeenCalledWith("bar-1", { width: 860 });
  });

  it("视图节点拖高按轴部分提交高度", () => {
    const onResizeNode = vi.fn();
    const { container } = renderNodeCard(viewNode("bar"), onResizeNode);
    const handle = container.querySelector(".node-resize-handle-bottom") as HTMLElement;

    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(handle, { clientX: 0, clientY: 100 });
    fireEvent.pointerUp(handle, { clientX: 0, clientY: 100 });
    expect(onResizeNode).toHaveBeenCalledWith("bar-1", { height: 460 });
  });
});

describe("NodeCard 详情节点默认宽度", () => {
  it("角色状态详情使用三列适配的默认宽度，伤害详情维持紧凑宽度", () => {
    const { container: attributeCard, unmount: unmountAttribute } = renderNodeCard(
      detailNode("attribute_detail"),
    );
    expect((attributeCard.querySelector(".node-card") as HTMLElement).style.width).toBe("640px");
    unmountAttribute();

    const { container: damageCard } = renderNodeCard(detailNode("damage_detail"));
    expect((damageCard.querySelector(".node-card") as HTMLElement).style.width).toBe("320px");
  });
});
