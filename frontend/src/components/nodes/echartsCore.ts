/** ECharts 按需引入与 React 薄封装：只注册柱状图所需能力，SVG 渲染器便于 DOM 呈现。 */

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import * as echarts from "echarts/core";
import { BarChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { ComposeOption, EChartsType } from "echarts/core";
import type { BarSeriesOption, PieSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";

echarts.use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer]);

/** 分析视图系列配色：首位与展示视图节点类别色对齐，其余取画布类别色的补充色相。 */
export const VIEW_CHART_PALETTE = [
  "#ef4444",
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#a855f7",
  "#14b8a6",
  "#ec4899",
  "#f97316",
  "#0ea5e9",
  "#6366f1",
];

/** 分析视图共用 option 类型：柱状图与饼图共用网格/图例/提示组件。 */
export type ChartOption = ComposeOption<
  | BarSeriesOption
  | PieSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TooltipComponentOption
>;

export type { EChartsType };

/**
 * 分析视图的 ECharts 生命周期封装：挂载初始化、容器尺寸变化跟随、
 * option 全量替换、点击回调与卸载清理。
 * option 为 null 表示视图处于无图状态（未绑定/错误提示），不初始化图表，
 * 恢复就绪时重新初始化。点击回调只透传系列下标与数据下标，
 * 数据项语义由调用方按当期数据解释。
 */
export function useEChartsView(
  containerRef: RefObject<HTMLDivElement | null>,
  option: ChartOption | null,
  onClickBar: (seriesIndex: number, dataIndex: number) => void,
): void {
  const chartRef = useRef<EChartsType | null>(null);
  const clickRef = useRef(onClickBar);
  useEffect(() => {
    clickRef.current = onClickBar;
  }, [onClickBar]);
  const ready = option !== null;

  useEffect(() => {
    const element = containerRef.current;
    if (element === null || !ready) {
      return;
    }
    const chart = echarts.init(element, null, { renderer: "svg" });
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [containerRef, ready]);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null || option === null) {
      return;
    }
    chart.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null) {
      return;
    }
    const handler = (params: unknown) => {
      const event = params as { componentType?: string; seriesIndex?: number; dataIndex?: number };
      if (event.componentType !== "series") {
        return;
      }
      clickRef.current(event.seriesIndex ?? -1, event.dataIndex ?? -1);
    };
    chart.on("click", handler);
    return () => {
      chart.off("click", handler);
    };
  }, []);
}
