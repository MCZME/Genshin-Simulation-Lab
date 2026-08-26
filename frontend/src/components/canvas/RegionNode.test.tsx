// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NodeProps } from "@xyflow/react";
import type { WorkflowRegion } from "../../workflow/types";
import { RegionNode, type RegionNodeData } from "./RegionNode";

const handleSpy = vi.hoisted(() => ({
  rendered: [] as Array<Record<string, unknown>>,
  connectionInProgress: false,
}));

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    Handle: (props: Record<string, unknown>) => {
      handleSpy.rendered.push(props);
      return null;
    },
    useReactFlow: () => ({
      screenToFlowPosition: () => ({ x: 0, y: 0 }),
    }),
    useStore: (selector: (state: unknown) => unknown) =>
      selector({ connection: { inProgress: handleSpy.connectionInProgress } }),
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
    onValidateRegion: vi.fn(),
    onRunRegion: vi.fn(),
    onRunAnalysis: vi.fn(),
    analysisRunPhase: null,
    interactionLocked: false,
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

beforeEach(() => {
  handleSpy.rendered.length = 0;
  handleSpy.connectionInProgress = false;
});

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

describe("RegionNode 区域运行", () => {
  it("点击区域校验调用 onValidateRegion（决策 2.40 修订）", () => {
    const onValidateRegion = vi.fn();
    renderRegion({ data: { onValidateRegion } });
    fireEvent.click(screen.getByRole("button", { name: "区域校验" }));
    expect(onValidateRegion).toHaveBeenCalledWith("region-1");
  });

  it("点击区域运行调用 onRunRegion（决策 2.40）", () => {
    const onRunRegion = vi.fn();
    renderRegion({ data: { onRunRegion } });
    fireEvent.click(screen.getByRole("button", { name: "区域运行" }));
    expect(onRunRegion).toHaveBeenCalledWith("region-1");
  });

  it("分析区域渲染运行分析按钮并调用 onRunAnalysis（2026-08-26）", () => {
    const onRunAnalysis = vi.fn();
    const analysisRegion: WorkflowRegion = {
      id: "region-1",
      kind: "analysis",
      name: "分析区",
      rect: { x: 0, y: 0, width: 880, height: 440 },
    };
    renderRegion({ data: { region: analysisRegion, onRunAnalysis } });
    fireEvent.click(screen.getByRole("button", { name: "运行分析" }));
    expect(onRunAnalysis).toHaveBeenCalledWith("region-1");
  });

  it("分析区域运行中显示阶段文本并禁用按钮（2026-08-26）", () => {
    const analysisRegion: WorkflowRegion = {
      id: "region-1",
      kind: "analysis",
      name: "分析区",
      rect: { x: 0, y: 0, width: 880, height: 440 },
    };
    renderRegion({
      data: {
        region: analysisRegion,
        analysisRunPhase: { regionId: "region-1", phase: "input" },
      },
    });
    expect(screen.getByText("获取输入…")).not.toBeNull();
    expect(
      (screen.getByRole("button", { name: "运行分析" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("配置区域不渲染运行分析按钮", () => {
    renderRegion();
    expect(screen.queryByRole("button", { name: "运行分析" })).toBeNull();
  });
});

describe("RegionNode 分析区域边界输入点", () => {
  const analysisRegion: WorkflowRegion = {
    id: "region-1",
    kind: "analysis",
    name: "分析区",
    rect: { x: 0, y: 0, width: 880, height: 440 },
  };

  function renderAnalysisRegion() {
    renderRegion({ data: { region: analysisRegion } });
  }

  it("输入点提供可发起连线的源把手，出边朝向区域内部", () => {
    renderAnalysisRegion();
    const sources = handleSpy.rendered.filter((props) => props.type === "source");
    expect(sources).toHaveLength(1);
    expect(sources[0].id).toBe("in");
    expect(sources[0].position).toBe("right");
    expect(sources[0].isConnectableEnd).toBe(false);
    const style = sources[0].style as Record<string, unknown>;
    expect(style.left).toBe(0);
    expect(style.transform).toBe("translate(-50%, -50%)");
    expect(style.pointerEvents).toBe("auto");
  });

  it("同一端口保留目标侧接收外部输入；连线进行中两侧互斥切换", () => {
    renderAnalysisRegion();
    const idleTargets = handleSpy.rendered.filter((props) => props.type === "target");
    expect(idleTargets).toHaveLength(1);
    expect(idleTargets[0].id).toBe("in");
    expect(idleTargets[0].isConnectableStart).toBe(false);
    expect((idleTargets[0].style as Record<string, unknown>).pointerEvents).toBe("none");

    handleSpy.rendered.length = 0;
    handleSpy.connectionInProgress = true;
    renderAnalysisRegion();
    const draggingTargets = handleSpy.rendered.filter((props) => props.type === "target");
    const draggingSources = handleSpy.rendered.filter((props) => props.type === "source");
    expect((draggingTargets[0].style as Record<string, unknown>).pointerEvents).toBe("auto");
    expect((draggingSources[0].style as Record<string, unknown>).pointerEvents).toBe("none");
  });

  it("配置区域不渲染 in 端口把手", () => {
    renderRegion();
    const inHandles = handleSpy.rendered.filter((props) => props.id === "in");
    expect(inHandles).toHaveLength(0);
  });
});
