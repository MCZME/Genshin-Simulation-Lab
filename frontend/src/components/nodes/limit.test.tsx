// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { LimitEditor } from "./analysis";

afterEach(() => {
  cleanup();
});

function limitNode(params: Record<string, unknown>): WorkflowNode {
  return {
    id: "limit-1",
    kind: "limit",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params,
  };
}

function Harness({
  node,
  onChange,
}: {
  node: WorkflowNode;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const [current, setCurrent] = useState(node);
  return (
    <LimitEditor
      node={current}
      onChange={(params) => {
        onChange(params);
        setCurrent({ ...current, params });
      }}
    />
  );
}

describe("限制行数节点编辑器（卡片直编）", () => {
  it("文案式输入：保留前 N 行", () => {
    render(<LimitEditor node={limitNode({ count: 1000 })} onChange={vi.fn()} />);
    expect(screen.getByText("保留前")).not.toBeNull();
    expect(screen.getByText("行")).not.toBeNull();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("1000");
  });

  it("输入数字即时写回 count", () => {
    const onChange = vi.fn();
    render(<Harness node={limitNode({})} onChange={onChange} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "10" } });

    expect(onChange).toHaveBeenLastCalledWith({ count: 10 });
  });

  it("清空输入删除 count 并提示", () => {
    const onChange = vi.fn();
    render(<Harness node={limitNode({ count: 1000 })} onChange={onChange} />);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "" } });

    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.getByText("请输入 1–10000 的整数")).not.toBeNull();
  });

  it("未设置时提示", () => {
    render(<LimitEditor node={limitNode({})} onChange={vi.fn()} />);
    expect(screen.getByText("请输入 1–10000 的整数")).not.toBeNull();
  });

  it("0 与超出上限提示", () => {
    render(<LimitEditor node={limitNode({ count: 0 })} onChange={vi.fn()} />);
    expect(screen.getByText("请输入 1–10000 的整数")).not.toBeNull();
  });

  it("非整数显示并提示", () => {
    render(<LimitEditor node={limitNode({ count: 1.5 })} onChange={vi.fn()} />);
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("1.5");
    expect(screen.getByText("请输入 1–10000 的整数")).not.toBeNull();
  });
});
