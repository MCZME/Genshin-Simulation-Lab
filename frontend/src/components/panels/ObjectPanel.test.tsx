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

  it("配置节点面板按类别分组", () => {
    render(<ObjectPanel onDragStart={vi.fn()} onCollapse={vi.fn()} />);
    const sections = Array.from(document.querySelectorAll(".panel-section"));
    const configSection = sections[1];
    const labels = Array.from(
      configSection.querySelectorAll(".panel-action-label"),
    ).map((item) => item.textContent);
    const subtitles = Array.from(
      configSection.querySelectorAll(".panel-subtitle"),
    ).map((item) => item.textContent);
    expect(subtitles).toEqual([
      "运行设置",
      "队伍配置",
      "目标配置",
      "操作输入",
      "变体扫描",
    ]);
    expect(labels).toEqual([
      "根节点",
      "元信息",
      "运行选项",
      "角色",
      "武器",
      "圣遗物",
      "目标",
      "按键轨迹",
      "枚举",
      "区间",
    ]);
  });

  it("分析节点面板按类别分组，单项详情独立于展示视图", () => {
    render(<ObjectPanel onDragStart={vi.fn()} onCollapse={vi.fn()} />);
    const sections = Array.from(document.querySelectorAll(".panel-section"));
    const analysisSection = sections[sections.length - 1];
    const labels = Array.from(
      analysisSection.querySelectorAll(".panel-action-label"),
    ).map((item) => item.textContent);
    const subtitles = Array.from(
      analysisSection.querySelectorAll(".panel-subtitle"),
    ).map((item) => item.textContent);
    expect(subtitles).toEqual([
      "数据获取",
      "数据加工",
      "展示配置",
      "展示视图",
      "单项详情",
    ]);
    expect(labels).toEqual([
      "获取数据",
      "过滤",
      "投影",
      "排序",
      "分组聚合",
      "限制行数",
      "合并表",
      "计算列",
      "构造列",
      "展开行",
      "取单项",
      "表格配置",
      "饼图配置",
      "柱状图配置",
      "表格",
      "饼图",
      "柱状图",
      "帧状态详情",
      "伤害详情",
      "状态详情",
      "角色状态详情",
    ]);
  });
});
