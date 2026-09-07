// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AnalysisNodeResult } from "../../workflow/analysis_runner";
import type { AnalysisTableResult } from "../../workflow/templates";
import type { WorkflowDefinition, WorkflowNode } from "../../workflow/types";
import { AnalysisResultsContext } from "../analysis_context";
import { AnalysisDetailBody } from "./detail";

afterEach(() => {
  cleanup();
});

function definitionWith(detail: WorkflowNode): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "t" },
    regions: [
      {
        id: "analysis-1",
        kind: "analysis",
        name: "分析",
        rect: { x: 0, y: 0, width: 600, height: 400 },
      },
    ],
    nodes: [
      {
        id: "runs1",
        kind: "fetch",
        region_id: "analysis-1",
        position: { x: 0, y: 0 },
        params: { source: "runs" },
      },
      detail,
    ],
    edges: [
      {
        id: "e1",
        source_node_id: "runs1",
        source_port_id: "out",
        target_node_id: detail.id,
        target_port_id: "in",
      },
    ],
    layout: {},
  };
}

function detailNode(): WorkflowNode {
  return {
    id: "detail1",
    kind: "state_detail",
    region_id: "analysis-1",
    position: { x: 100, y: 0 },
    params: {},
  };
}

function resultWith(rows: unknown[][]): AnalysisNodeResult {
  const table: AnalysisTableResult = {
    columns: [
      { name: "session_id", type: "string" },
      { name: "frame", type: "int" },
    ],
    rows,
    truncated: false,
  };
  return { status: "ready", table };
}

function renderDetail(result: AnalysisNodeResult): void {
  const detail = detailNode();
  const definition = definitionWith(detail);
  render(
    <AnalysisResultsContext.Provider
      value={new Map([["runs1", result]])}
    >
      <AnalysisDetailBody
        node={detail}
        definition={definition}
      />
    </AnalysisResultsContext.Provider>,
  );
}

describe("单项详情节点输入行数语义", () => {
  it("0 行显示无数据", () => {
    renderDetail(resultWith([]));
    expect(screen.getByText(/无数据/)).not.toBeNull();
  });

  it("1 行渲染详情", () => {
    renderDetail(resultWith([["s-1", 120]]));
    expect(screen.getByText(/状态实例/)).not.toBeNull();
    expect(screen.getByText(/"session_id": "s-1"/)).not.toBeNull();
  });

  it("≥2 行报错而不是静默取首行", () => {
    renderDetail(
      resultWith([
        ["s-1", 120],
        ["s-2", 240],
      ]),
    );
    expect(screen.getByText(/需要单行表，当前 2 行/)).not.toBeNull();
  });
});
