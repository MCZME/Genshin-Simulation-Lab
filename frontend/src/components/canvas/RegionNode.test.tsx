// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NodeProps } from "@xyflow/react";
import type { WorkflowRegion } from "../../workflow/types";
import { RegionNode, type RegionNodeData } from "./RegionNode";

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    Handle: () => null,
    useReactFlow: () => ({
      screenToFlowPosition: () => ({ x: 0, y: 0 }),
    }),
    useStore: (selector: (state: unknown) => unknown) =>
      selector({ connection: { inProgress: false } }),
  };
});

const region: WorkflowRegion = {
  id: "region-1",
  kind: "configuration",
  name: "主配置",
  rect: { x: 0, y: 0, width: 880, height: 440 },
};

function renderRegion(
  overrides: Partial<{
    data: Partial<RegionNodeData>;
    selected: boolean;
  }> = {},
) {
  const data: RegionNodeData = {
    region,
    onDeleteRegion: vi.fn(),
    onRenameRegion: vi.fn(),
    onResizeRegion: vi.fn(),
    onMoveEdgeOrder: vi.fn(),
    incomingGroups: [],
    dropTarget: false,
    renameRequested: false,
    onRenameRequestHandled: vi.fn(),
    ...overrides.data,
  };
  const props = {
    id: "region-1",
    data,
    selected: overrides.selected ?? false,
    width: 880,
    height: 440,
  } as unknown as NodeProps;
  return render(
    <RegionNode {...props} />,
  );
}

afterEach(cleanup);

describe("RegionNode 区域命名", () => {
  it("双击名称进入编辑并提交重命名", () => {
    const onRenameRegion = vi.fn();
    renderRegion({ data: { onRenameRegion } });
    fireEvent.doubleClick(screen.getByText("主配置"));

    const input = screen.getByRole("textbox", { name: "区域名称" });
    fireEvent.change(input, { target: { value: "主输出配置" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRenameRegion).toHaveBeenCalledWith("region-1", "主输出配置");
  });

  it("铅笔按钮同样进入编辑并支持失焦提交", () => {
    const onRenameRegion = vi.fn();
    renderRegion({ data: { onRenameRegion } });
    fireEvent.click(screen.getByRole("button", { name: "重命名区域 主配置" }));

    const input = screen.getByRole("textbox", { name: "区域名称" });
    fireEvent.change(input, { target: { value: "副配置" } });
    fireEvent.blur(input);
    expect(onRenameRegion).toHaveBeenCalledWith("region-1", "副配置");
  });

  it("Esc 取消编辑不提交", () => {
    const onRenameRegion = vi.fn();
    renderRegion({ data: { onRenameRegion } });
    fireEvent.doubleClick(screen.getByText("主配置"));
    const input = screen.getByRole("textbox", { name: "区域名称" });
    fireEvent.change(input, { target: { value: "不应提交" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onRenameRegion).not.toHaveBeenCalled();
    expect(screen.getByText("主配置")).toBeTruthy();
  });

  it("空名或全空格不提交并恢复原名", () => {
    const onRenameRegion = vi.fn();
    renderRegion({ data: { onRenameRegion } });
    fireEvent.doubleClick(screen.getByText("主配置"));
    const input = screen.getByRole("textbox", { name: "区域名称" });
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRenameRegion).not.toHaveBeenCalled();
    expect(screen.getByText("主配置")).toBeTruthy();
  });

  it("新区域创建请求自动进入命名态并回调清除", () => {
    const onRenameRegion = vi.fn();
    const onRenameRequestHandled = vi.fn();
    renderRegion({
      data: {
        onRenameRegion,
        onRenameRequestHandled,
        renameRequested: true,
      },
    });
    expect(onRenameRequestHandled).toHaveBeenCalledTimes(1);
    const input = screen.getByRole("textbox", { name: "区域名称" });
    fireEvent.change(input, { target: { value: "深渊配队" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRenameRegion).toHaveBeenCalledWith("region-1", "深渊配队");
  });
});
