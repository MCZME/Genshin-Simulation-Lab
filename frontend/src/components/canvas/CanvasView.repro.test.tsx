// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CanvasView } from "./CanvasView";
import type { WorkflowDefinition } from "../../workflow/types";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

const definition: WorkflowDefinition = {
  schema_version: 1,
  meta: { name: "复现" },
  regions: [
    {
      id: "region-1",
      kind: "configuration",
      name: "主配置",
      rect: { x: 40, y: 40, width: 880, height: 440 },
    },
  ],
  nodes: [
    {
      id: "node-root",
      kind: "root",
      region_id: "region-1",
      position: { x: 60, y: 80 },
      params: {},
    },
    {
      id: "node-sim",
      kind: "simulation",
      region_id: null,
      position: { x: 500, y: 560 },
      params: {},
    },
  ],
  edges: [
    {
      id: "edge-1",
      source_node_id: "region-1",
      source_port_id: "out",
      target_node_id: "node-sim",
      target_port_id: "in",
    },
  ],
  layout: {},
};

describe("CanvasView repro", () => {
  it("渲染父容器区域不进入更新循环", () => {
    render(
      <CanvasView
        definition={definition}
        selection={{ regions: [], nodes: [], edges: [] }}
        diagnostics={[]}
        dragKind={null}
        selectionEpoch={0}
        viewportCommand={null}
        renameRegionRequestId={null}
        dimmedNodeIds={[]}
        runningMethodNodeIds={[]}
        interactionLocked={false}
        onViewportCommandHandled={() => undefined}
        onRenameRegionRequestHandled={() => undefined}
        onMoveNode={() => undefined}
        onMoveRegion={() => undefined}
        onResizeRegion={() => undefined}
        onRenameRegion={() => undefined}
        onValidateRegion={() => undefined}
        onRunRegion={() => undefined}
        onConnectEdge={() => undefined}
        onSelect={() => undefined}
        onParamsChange={() => undefined}
        onDeleteNode={() => undefined}
        onDeleteEdge={() => undefined}
        onDeleteRegion={() => undefined}
        onLocateNode={() => undefined}
        onDropObject={() => undefined}
        onMoveEdgeOrder={() => undefined}
      />,
    );
    const regionNode = screen.getByTestId("rf__node-region-1");
    expect(regionNode.classList).toContain("draggable");
    expect(regionNode.classList).toContain("nopan");
  });
});
