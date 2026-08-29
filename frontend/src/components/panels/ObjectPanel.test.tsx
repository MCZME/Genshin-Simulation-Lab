// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ObjectPanel } from "./ObjectPanel";

describe("ObjectPanel", () => {
  afterEach(cleanup);

  it("点击收起按钮触发 onCollapse", () => {
    const onCollapse = vi.fn();
    render(<ObjectPanel onDragStart={vi.fn()} onCollapse={onCollapse} />);

    fireEvent.click(screen.getByRole("button", { name: "收起节点面板" }));

    expect(onCollapse).toHaveBeenCalledTimes(1);
  });

  it("分析节点面板中展示配置与对应视图相邻", () => {
    render(<ObjectPanel onDragStart={vi.fn()} onCollapse={vi.fn()} />);
    const sections = Array.from(document.querySelectorAll(".panel-section"));
    const analysisSection = sections[sections.length - 1];
    const labels = Array.from(
      analysisSection.querySelectorAll(".panel-action-label"),
    ).map((item) => item.textContent);
    expect(labels).toEqual([
      "获取数据",
      "过滤",
      "投影",
      "排序",
      "分组聚合",
      "限制行数",
      "合并表",
      "计算列",
      "取单项",
      "表格配置",
      "表格",
      "饼图配置",
      "饼图",
      "柱状图配置",
      "指标柱状图",
      "帧状态详情",
      "伤害详情",
      "状态详情",
      "属性详情",
    ]);
  });
});
