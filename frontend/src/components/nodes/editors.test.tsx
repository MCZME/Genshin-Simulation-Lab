// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { CharacterEditor, MetaEditor } from "./editors";

function characterNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "node-1",
    kind: "character",
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: {
      slot: 1,
      asset: "",
      level: 90,
      constellation: 0,
      talents: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
    },
    ...overrides,
  };
}

afterEach(cleanup);

describe("固定路径节点的编辑器", () => {
  it("角色编辑器不提供路径编辑入口", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    expect(screen.queryByText("目标路径")).toBeNull();
    expect(screen.queryByText("高级")).toBeNull();
  });

  it("元信息编辑器提供名称与描述配置", () => {
    const onChange = vi.fn();
    render(
      <MetaEditor
        node={characterNode({ kind: "meta" })}
        onChange={onChange}
      />,
    );
    expect(screen.getByLabelText("名称")).toBeTruthy();
    expect(screen.getByLabelText("描述")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("名称"), {
      target: { value: "深渊满星队" },
    });
    fireEvent.blur(screen.getByLabelText("名称"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ name: "深渊满星队" }));
    expect(screen.queryByText("目标路径")).toBeNull();
    expect(screen.queryByText("高级")).toBeNull();
  });
});
