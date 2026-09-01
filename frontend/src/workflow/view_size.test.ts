import { describe, expect, it } from "vitest";
import {
  MAX_BAR_FIT_HEIGHT,
  MAX_VIEW_HEIGHT,
  MIN_VIEW_WIDTH,
  VIEW_SOFT_CAP_WIDTH,
  resolveBarHeight,
  resolveManualViewWidth,
  resolveViewHeight,
  resolveViewWidth,
} from "./view_size";

describe("view_size 宽度解析", () => {
  it("内容驱动宽度：自动模式取 min(内容自然宽, 软上限)，未测量用最小宽", () => {
    expect(resolveViewWidth(null, undefined)).toBe(MIN_VIEW_WIDTH);
    expect(resolveViewWidth(700, undefined)).toBe(700);
    expect(resolveViewWidth(1200, undefined)).toBe(VIEW_SOFT_CAP_WIDTH);
  });

  it("内容驱动宽度：手动宽度夹持在 [最小宽, 内容自然宽]，未测量回落软上限", () => {
    expect(resolveViewWidth(800, 700)).toBe(700);
    expect(resolveViewWidth(800, 1000)).toBe(800);
    expect(resolveViewWidth(null, 1000)).toBe(VIEW_SOFT_CAP_WIDTH);
    expect(resolveViewWidth(400, 1000)).toBe(560);
    expect(resolveViewWidth(800, 300)).toBe(560);
  });

  it("饼图手动宽度夹持在 [最小宽, 软上限]", () => {
    expect(resolveManualViewWidth(undefined)).toBe(MIN_VIEW_WIDTH);
    expect(resolveManualViewWidth(720)).toBe(720);
    expect(resolveManualViewWidth(1200)).toBe(VIEW_SOFT_CAP_WIDTH);
  });
});

describe("view_size 高度解析", () => {
  it("柱状图高度自动模式：min(内容估算高, 高度软上限)，未测量用默认高", () => {
    expect(resolveBarHeight(null, undefined)).toBe(360);
    expect(resolveBarHeight(400, undefined)).toBe(400);
    expect(resolveBarHeight(MAX_BAR_FIT_HEIGHT, undefined)).toBe(MAX_VIEW_HEIGHT);
  });

  it("柱状图高度手动模式：夹持在 [最小高, 内容估算高]，未测量回落高度软上限", () => {
    expect(resolveBarHeight(500, 600)).toBe(500);
    expect(resolveBarHeight(500, 300)).toBe(300);
    expect(resolveBarHeight(null, 700)).toBe(700);
  });

  it("普通视图高度纯手动", () => {
    expect(resolveViewHeight(undefined)).toBe(360);
    expect(resolveViewHeight(500)).toBe(500);
    expect(resolveViewHeight(999)).toBe(MAX_VIEW_HEIGHT);
  });
});
