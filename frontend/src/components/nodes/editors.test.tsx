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

  it("角色编辑器槽位显示数字并进入滑块编辑", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    const slot = screen.getByLabelText("槽位");
    expect(slot.tagName).toBe("BUTTON");
    expect(slot.textContent).toBe("1");
    fireEvent.click(slot);
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("type")).toBe("range");
    expect(slider.getAttribute("min")).toBe("0");
    expect(slider.getAttribute("max")).toBe("3");
  });

  it("角色编辑器等级滑块覆盖 1-90 与 95、100", () => {
    render(<CharacterEditor node={characterNode()} onChange={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("等级"));
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("max")).toBe("91");
  });

  it("角色编辑器提供三项天赋并提交修改", () => {
    const onChange = vi.fn();
    render(<CharacterEditor node={characterNode()} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("元素爆发"));
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "8" } });
    fireEvent.blur(slider);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        talents: expect.objectContaining({ elemental_burst: 9 }),
      }),
    );
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
