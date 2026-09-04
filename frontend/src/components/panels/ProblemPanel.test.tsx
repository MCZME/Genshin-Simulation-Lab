// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Diagnostic } from "../../workflow/types";
import { ProblemPanel } from "./ProblemPanel";

const diagnostics: Diagnostic[] = [
  {
    severity: "error",
    code: "CYCLE_DETECTED",
    message: "工作流图存在环",
    node_id: "node-1",
    edge_id: null,
    region_id: null,
    path: null,
  },
  {
    severity: "warning",
    code: "PATH_OVERRIDE",
    message: "同路径片段被覆盖",
    node_id: "node-2",
    edge_id: null,
    region_id: null,
    path: "team[0].character",
  },
];

afterEach(cleanup);

describe("ProblemPanel", () => {
  it("展示全部诊断并支持按严重程度筛选", () => {
    render(<ProblemPanel diagnostics={diagnostics} onLocate={vi.fn()} />);
    expect(screen.getByText("工作流图存在环")).toBeTruthy();
    expect(screen.getByText("同路径片段被覆盖")).toBeTruthy();

    fireEvent.click(screen.getByText("错误"));
    expect(screen.queryByText("同路径片段被覆盖")).toBeNull();
    expect(screen.getByText("工作流图存在环")).toBeTruthy();
  });

  it("点击诊断项触发定位", () => {
    const onLocate = vi.fn();
    render(<ProblemPanel diagnostics={diagnostics} onLocate={onLocate} />);
    fireEvent.click(screen.getByText("工作流图存在环"));
    expect(onLocate).toHaveBeenCalledWith(diagnostics[0]);
  });
});
