// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WorkflowNode } from "../../workflow/types";
import { EnumEditor, RangeEditor } from "./variants";

vi.mock("../../api/client", () => ({
  searchAssets: vi.fn().mockResolvedValue({ items: [] }),
  getAsset: vi.fn().mockResolvedValue(null),
}));

function makeNode(
  kind: "enum" | "range",
  params: Record<string, unknown>,
): WorkflowNode {
  return { id: "node-1", kind, region_id: "region-1", position: { x: 0, y: 0 }, params };
}

afterEach(cleanup);

describe("EnumEditor", () => {
  const assetDimensionNode = makeNode("enum", {
    dimension: "character.asset_key",
    path_params: { slot: 1 },
    values: [{ item_id: "e-1", value: "character:barbara", label: null }],
  });

  it("维度模式显示推导路径", () => {
    render(<EnumEditor node={assetDimensionNode} onChange={() => {}} />);
    expect(screen.getByText("team[0].character")).toBeTruthy();
    expect(screen.getByText("常用维度").className).toContain("active");
  });

  it("切换到自定义路径携带当前推导路径与值类型", () => {
    const onChange = vi.fn();
    render(<EnumEditor node={assetDimensionNode} onChange={onChange} />);
    fireEvent.click(screen.getByText("自定义路径"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        dimension: null,
        path: "team[0].character",
        value_type: "asset",
      }),
    );
  });

  it("切换维度重置路径参数与取值", () => {
    const onChange = vi.fn();
    render(<EnumEditor node={assetDimensionNode} onChange={onChange} />);
    fireEvent.change(screen.getByDisplayValue("角色"), {
      target: { value: "character.constellation" },
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        dimension: "character.constellation",
        path_params: { slot: 1 },
        values: [{ item_id: "e-2", value: 0, label: null }],
      }),
    );
  });

  it("自定义模式保留路径与值类型编辑", () => {
    render(
      <EnumEditor
        node={makeNode("enum", {
          dimension: null,
          path: "team[0].character.constellation",
          value_type: "number",
          values: [{ item_id: "e-1", value: 0, label: null }],
        })}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("自定义路径").className).toContain("active");
    expect(screen.getByDisplayValue("team[0].character.constellation")).toBeTruthy();
    expect(screen.getByDisplayValue("数值")).toBeTruthy();
  });
});

describe("RangeEditor", () => {
  it("百分比维度按百分比显示存储的小数值", () => {
    render(
      <RangeEditor
        node={makeNode("range", {
          dimension: "target.resistance",
          path_params: { target_index: 0, choice: "pyro" },
          start: 0.4,
          end: 0.4,
          step: 0.1,
          label: null,
        })}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("scene.targets[0].resistance.pyro")).toBeTruthy();
    expect(screen.getAllByText("40%")).toHaveLength(2);
    expect(screen.getByText("10%")).toBeTruthy();
  });

  it("切换维度时按维度默认区间重置", () => {
    const onChange = vi.fn();
    render(
      <RangeEditor
        node={makeNode("range", {
          dimension: "target.resistance",
          path_params: { target_index: 0, choice: "physical" },
          start: 0,
          end: 0.4,
          step: 0.1,
          label: null,
        })}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByDisplayValue("目标抗性"), {
      target: { value: "character.level" },
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        dimension: "character.level",
        path_params: { slot: 1 },
        start: 1,
        end: 90,
        step: 1,
      }),
    );
  });

  it("维度模式显示推导路径", () => {
    render(
      <RangeEditor
        node={makeNode("range", {
          dimension: "character.talents",
          path_params: { slot: 2, choice: "elemental_burst" },
          start: 1,
          end: 10,
          step: 1,
          label: null,
        })}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("team[1].character.talents.elemental_burst")).toBeTruthy();
  });
});
