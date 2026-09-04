// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowListItem } from "../../api/client";
import { TopBar } from "./TopBar";

const workflows: WorkflowListItem[] = [
  { id: "wf_a", name: "主配队", updated_at: "2026-08-20T10:00:00+00:00" },
  { id: "wf_b", name: "深渊上半", updated_at: "2026-08-19T10:00:00+00:00" },
];

function renderTopBar(overrides: Partial<Parameters<typeof TopBar>[0]> = {}) {
  const props = {
    name: "主配队",
    dirty: false,
    saving: false,
    running: false,
    canRun: true,
    canUndo: true,
    canRedo: true,
    workflows,
    workflowId: "wf_a",
    onRename: vi.fn(),
    onUndo: vi.fn(),
    onRedo: vi.fn(),
    onSave: vi.fn(),
    onRun: vi.fn(),
    onCancelRun: vi.fn(),
    onCreate: vi.fn(),
    onSaveAndCreate: vi.fn(),
    onSwitch: vi.fn(),
    onSaveAndSwitch: vi.fn(),
    onDelete: vi.fn(),
    onRenameWorkflow: vi.fn(),
    ...overrides,
  };
  return render(<TopBar {...props} />);
}

afterEach(cleanup);

describe("TopBar 工作流切换器", () => {
  it("顶栏右侧提供撤销与重做并触发回调", () => {
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    renderTopBar({ onUndo, onRedo });
    fireEvent.click(screen.getByTitle("撤销 (Ctrl+Z)"));
    fireEvent.click(screen.getByTitle("重做 (Ctrl+Shift+Z / Ctrl+Y)"));
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(onRedo).toHaveBeenCalledTimes(1);
  });

  it("运行期间运行按钮可点击，双击触发整次取消（决策 2.38）", () => {
    const onRun = vi.fn();
    const onCancelRun = vi.fn();
    renderTopBar({ running: true, canRun: false, onRun, onCancelRun });
    const button = screen.getByRole("button", { name: "运行中…" });
    expect(button.hasAttribute("disabled")).toBe(false);
    // 单击不触发任何动作。
    fireEvent.click(button);
    expect(onRun).not.toHaveBeenCalled();
    expect(onCancelRun).not.toHaveBeenCalled();
    fireEvent.doubleClick(button);
    expect(onCancelRun).toHaveBeenCalledTimes(1);
    expect(onRun).not.toHaveBeenCalled();
  });

  it("非运行期间单击触发运行", () => {
    const onRun = vi.fn();
    const onCancelRun = vi.fn();
    renderTopBar({ running: false, canRun: true, onRun, onCancelRun });
    fireEvent.click(screen.getByRole("button", { name: "全部运行" }));
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onCancelRun).not.toHaveBeenCalled();
  });

  it("不可撤销时禁用撤销按钮", () => {
    renderTopBar({ canUndo: false });
    expect(screen.getByTitle("撤销 (Ctrl+Z)").hasAttribute("disabled")).toBe(true);
    expect(screen.getByTitle("重做 (Ctrl+Shift+Z / Ctrl+Y)").hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("打开菜单展示工作流列表与新建入口", () => {
    renderTopBar();
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    expect(screen.getByText("主配队")).toBeTruthy();
    expect(screen.getByText("深渊上半")).toBeTruthy();
    expect(screen.getByText("＋ 新建工作流")).toBeTruthy();
  });

  it("无未保存改动时点击其他工作流直接切换", () => {
    const onSwitch = vi.fn();
    renderTopBar({ onSwitch });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("深渊上半"));
    expect(onSwitch).toHaveBeenCalledWith("wf_b");
    expect(screen.queryByText("＋ 新建工作流")).toBeNull();
  });

  it("点击当前工作流只关闭菜单", () => {
    const onSwitch = vi.fn();
    renderTopBar({ onSwitch });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("主配队"));
    expect(onSwitch).not.toHaveBeenCalled();
    expect(screen.queryByText("＋ 新建工作流")).toBeNull();
  });

  it("有未保存改动时切换需三选确认", () => {
    const onSwitch = vi.fn();
    const onSaveAndSwitch = vi.fn();
    renderTopBar({ dirty: true, onSwitch, onSaveAndSwitch });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("深渊上半"));

    expect(screen.getByText("当前工作流有未保存改动")).toBeTruthy();
    fireEvent.click(screen.getByText("保存并切换"));
    expect(onSaveAndSwitch).toHaveBeenCalledWith("wf_b");
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it("确认视图可选择不保存切换", () => {
    const onSwitch = vi.fn();
    renderTopBar({ dirty: true, onSwitch });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("深渊上半"));
    fireEvent.click(screen.getByText("不保存切换"));
    expect(onSwitch).toHaveBeenCalledWith("wf_b");
  });

  it("确认视图取消后回到列表", () => {
    renderTopBar({ dirty: true });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("深渊上半"));
    fireEvent.click(screen.getByText("取消"));
    expect(screen.getByText("＋ 新建工作流")).toBeTruthy();
    expect(screen.queryByText("当前工作流有未保存改动")).toBeNull();
  });

  it("新建工作流在无改动时直接创建", () => {
    const onCreate = vi.fn();
    renderTopBar({ onCreate });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("＋ 新建工作流"));
    expect(onCreate).toHaveBeenCalled();
  });

  it("有未保存改动时新建进入三选确认", () => {
    const onCreate = vi.fn();
    const onSaveAndCreate = vi.fn();
    renderTopBar({ dirty: true, onCreate, onSaveAndCreate });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByText("＋ 新建工作流"));
    fireEvent.click(screen.getByText("保存并新建"));
    expect(onSaveAndCreate).toHaveBeenCalled();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("行内重命名当前工作流走本地重命名", () => {
    const onRename = vi.fn();
    renderTopBar({ onRename });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByRole("button", { name: "重命名 主配队" }));
    const input = screen.getByRole("textbox", { name: "重命名工作流" });
    fireEvent.change(input, { target: { value: "新名字" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRename).toHaveBeenCalledWith("新名字");
  });

  it("行内重命名非当前工作流走存档重命名", () => {
    const onRenameWorkflow = vi.fn();
    renderTopBar({ onRenameWorkflow });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByRole("button", { name: "重命名 深渊上半" }));
    const input = screen.getByRole("textbox", { name: "重命名工作流" });
    fireEvent.change(input, { target: { value: "深渊下半" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRenameWorkflow).toHaveBeenCalledWith("wf_b", "深渊下半");
  });

  it("删除工作流需二次确认", () => {
    const onDelete = vi.fn();
    renderTopBar({ onDelete });
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    fireEvent.click(screen.getByRole("button", { name: "删除 深渊上半" }));
    expect(screen.getByText("删除「深渊上半」？")).toBeTruthy();
    fireEvent.click(screen.getByText("删除"));
    expect(onDelete).toHaveBeenCalledWith("wf_b");
  });

  it("运行中禁用切换器", () => {
    renderTopBar({ running: true });
    const toggle = screen.getByRole("button", { name: "切换工作流" });
    expect(toggle.hasAttribute("disabled")).toBe(true);
    fireEvent.click(toggle);
    expect(screen.queryByText("＋ 新建工作流")).toBeNull();
  });

  it("点击切换器外部关闭菜单", () => {
    renderTopBar();
    fireEvent.click(screen.getByRole("button", { name: "切换工作流" }));
    expect(screen.getByText("＋ 新建工作流")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("＋ 新建工作流")).toBeNull();
  });
});
