// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getResultDetail, listResults } from "../../api/client";
import type { RunDetailResponse, RunListItem } from "../../api/client";
import { ResultsPanel } from "./ResultsPanel";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listResults: vi.fn(),
    getResultDetail: vi.fn(),
  };
});

const mockedList = vi.mocked(listResults);
const mockedDetail = vi.mocked(getResultDetail);

function listItem(overrides: Partial<RunListItem> = {}): RunListItem {
  return {
    session_id: "s-1",
    state: "completed",
    name: "主配置",
    stop_reason: "INPUT_EXHAUSTED",
    end_frame: 600,
    frames_run: 600,
    created_at: "2026-08-22T10:00:00+00:00",
    event_count: 128,
    ...overrides,
  };
}

function detail(overrides: Partial<RunDetailResponse> = {}): RunDetailResponse {
  return {
    session_id: "s-1",
    state: "completed",
    name: "主配置",
    summary: { stop_reason: "INPUT_EXHAUSTED", end_frame: 600, frames_run: 600 },
    error_code: null,
    error_message: null,
    created_at: "2026-08-22T10:00:00+00:00",
    started_at: "2026-08-22T10:00:01+00:00",
    finished_at: "2026-08-22T10:00:08+00:00",
    event_count: 128,
    ...overrides,
  };
}

function renderPanel(props: Partial<Parameters<typeof ResultsPanel>[0]> = {}) {
  return render(
    <ResultsPanel
      focusSessionId={null}
      onFocusHandled={vi.fn()}
      onCollapse={vi.fn()}
      {...props}
    />,
  );
}

afterEach(cleanup);

describe("ResultsPanel（结果库历史浏览器，决策 2.37）", () => {
  it("挂载时加载列表并渲染记录行", async () => {
    mockedList.mockResolvedValue({
      items: [
        listItem(),
        listItem({ session_id: "s-2", state: "failed", name: "" }),
      ],
    });

    renderPanel();

    expect(await screen.findByText("主配置")).not.toBeNull();
    // 「成功/失败」同时出现在筛选按钮与状态徽标上，断言至少存在一处。
    expect(screen.getAllByText("成功").length).toBeGreaterThan(0);
    expect(screen.getAllByText("失败").length).toBeGreaterThan(0);
    expect(screen.getByText("未命名运行")).not.toBeNull();
    expect(mockedList).toHaveBeenCalledWith(
      expect.objectContaining({ state: undefined, limit: 50, offset: 0 }),
    );
  });

  it("状态筛选切换时带 state 参数重新加载", async () => {
    mockedList.mockResolvedValue({ items: [listItem()] });
    renderPanel();
    await screen.findByText("主配置");

    fireEvent.click(screen.getByRole("button", { name: "失败" }));
    await waitFor(() => {
      expect(mockedList).toHaveBeenLastCalledWith(
        expect.objectContaining({ state: "failed", offset: 0 }),
      );
    });
  });

  it("点击记录打开详情概要", async () => {
    mockedList.mockResolvedValue({ items: [listItem()] });
    mockedDetail.mockResolvedValue(detail());
    renderPanel();
    fireEvent.click(await screen.findByText("主配置"));

    expect(await screen.findByText("INPUT_EXHAUSTED")).not.toBeNull();
    expect(screen.getByText("10.0 秒（600 帧）")).not.toBeNull();
    expect(screen.getByText("s-1")).not.toBeNull();
    expect(mockedDetail).toHaveBeenCalledWith("s-1");

    fireEvent.click(screen.getByRole("button", { name: "‹ 返回" }));
    expect(await screen.findByText("主配置")).not.toBeNull();
  });

  it("失败记录详情显示错误码与错误信息", async () => {
    mockedList.mockResolvedValue({ items: [listItem({ state: "failed", session_id: "s-3" })] });
    mockedDetail.mockResolvedValue(
      detail({
        session_id: "s-3",
        state: "failed",
        summary: null,
        error_code: "SIMULATION_FAILED",
        error_message: "第 120 帧断言失败",
      }),
    );
    renderPanel();
    fireEvent.click(await screen.findByText("主配置"));

    expect(await screen.findByText("SIMULATION_FAILED")).not.toBeNull();
    expect(screen.getByText("第 120 帧断言失败")).not.toBeNull();
    // 无 summary 时结束原因与时长均显示占位。
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("定位请求打开对应记录详情并回调完成", async () => {
    mockedList.mockResolvedValue({ items: [listItem()] });
    mockedDetail.mockResolvedValue(detail({ session_id: "s-9" }));
    const onFocusHandled = vi.fn();
    renderPanel({ focusSessionId: "s-9", onFocusHandled });

    expect(await screen.findByText("INPUT_EXHAUSTED")).not.toBeNull();
    expect(mockedDetail).toHaveBeenCalledWith("s-9");
    expect(onFocusHandled).toHaveBeenCalled();
  });

  it("列表加载失败显示错误提示", async () => {
    mockedList.mockRejectedValue(new Error("结果库不可用"));
    renderPanel();

    expect(await screen.findByText("结果库不可用")).not.toBeNull();
  });
});
