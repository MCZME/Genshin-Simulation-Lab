// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { listResults } from "../../api/client";
import type { RunListItem } from "../../api/client";
import type { WorkflowNode } from "../../workflow/types";
import { DataProviderEditor } from "./dataProvider";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    listResults: vi.fn(),
  };
});

const mockedList = vi.mocked(listResults);

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

function providerNode(
  sessionIds: string[],
): WorkflowNode {
  return {
    id: "provider-1",
    kind: "data_provider",
    region_id: null,
    position: { x: 0, y: 0 },
    params: { session_ids: sessionIds },
  };
}

function Harness({ node }: { node: WorkflowNode }) {
  const [current, setCurrent] = useState(node);
  return (
    <DataProviderEditor
      node={current}
      onChange={(params) => setCurrent({ ...current, params })}
    />
  );
}

const ALL_RUNS: RunListItem[] = [
  listItem({ session_id: "s-1", name: "运行 s-1" }),
  listItem({ session_id: "s-2", name: "运行 s-2" }),
  listItem({ session_id: "s-3", name: "扫荡测试" }),
];

function mockResults(options: {
  ids?: string[];
  q?: string;
  state?: "completed" | "failed" | "cancelled";
}) {
  let items = ALL_RUNS;
  if (options.ids !== undefined) {
    items = ALL_RUNS.filter((item) => options.ids?.includes(item.session_id));
  }
  const query = (options.q ?? "").trim().toLowerCase();
  if (query !== "") {
    items = items.filter((item) => item.name.toLowerCase().includes(query));
  }
  if (options.state !== undefined) {
    items = items.filter((item) => item.state === options.state);
  }
  return { items };
}

afterEach(() => {
  cleanup();
  mockedList.mockReset();
});

describe("数据提供节点编辑器（摘要 + 选择弹层）", () => {
  it("节点卡摘要显示已选数量与名称，空选择显示提示", async () => {
    mockedList.mockImplementation(async (options = {}) => mockResults(options));

    const { rerender } = render(<Harness node={providerNode(["s-1"])} />);

    expect(await screen.findByText(/已选 1 场/)).not.toBeNull();
    expect(await screen.findByText("运行 s-1")).not.toBeNull();

    rerender(<Harness key="empty" node={providerNode([])} />);

    expect(screen.getByText(/已选 0 场/)).not.toBeNull();
    expect(screen.getByText(/未选择会话/)).not.toBeNull();
  });

  it("弹层选择会话后按顺序提交 session_ids", async () => {
    mockedList.mockImplementation(async (options = {}) => mockResults(options));
    const onChange = vi.fn();

    render(<DataProviderEditor node={providerNode([])} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "选择会话" }));
    expect(await screen.findByRole("dialog")).not.toBeNull();
    expect(await screen.findByText("运行 s-1")).not.toBeNull();

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[1]);
    fireEvent.click(checkboxes[2]);
    fireEvent.click(screen.getAllByTitle("下移")[0]);
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onChange).toHaveBeenCalledWith({ session_ids: ["s-2", "s-1"] });
  });

  it("失效会话在摘要中提示并可一键清除", async () => {
    mockedList.mockImplementation(async (options = {}) => mockResults(options));
    const onChange = vi.fn();

    render(
      <DataProviderEditor
        node={providerNode(["s-1", "s-missing"])}
        onChange={onChange}
      />,
    );

    expect(await screen.findByText(/1 场已不存在/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "清除失效" }));

    expect(onChange).toHaveBeenCalledWith({ session_ids: ["s-1"] });
  });

  it("按名称搜索只返回匹配会话并向后端传 q", async () => {
    mockedList.mockImplementation(async (options = {}) => mockResults(options));

    render(<DataProviderEditor node={providerNode([])} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "选择会话" }));
    expect(await screen.findByRole("dialog")).not.toBeNull();
    expect(await screen.findByText("运行 s-1")).not.toBeNull();

    const search = screen.getByPlaceholderText("按名称搜索…");
    fireEvent.change(search, { target: { value: "扫荡" } });

    await waitFor(() => expect(screen.queryByText("运行 s-1")).toBeNull());
    expect(screen.getByText("扫荡测试")).not.toBeNull();
    expect(screen.queryByText("运行 s-2")).toBeNull();
    expect(mockedList).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "扫荡" }),
    );
  });
});
