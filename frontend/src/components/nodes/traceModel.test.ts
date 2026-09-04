import { describe, expect, it } from "vitest";
import type { TraceBlock } from "./traceModel";
import {
  DEFAULT_TAP_FRAMES,
  FRAME_MS,
  MIN_TIMELINE_FRAMES,
  TIMELINE_TAIL_FRAMES,
  TRACE_MAX_FRAME,
  blockToTimelineItem,
  blocksToItems,
  buildBlocks,
  clampBlockEdit,
  clampMovePress,
  clampTracePress,
  clampTraceRelease,
  computeGhostPlacement,
  formatSecondsLabel,
  formatTraceSeconds,
  frameFromViewport,
  frameToMs,
  dateToFrame,
  layoutBlocks,
  maxFrameOf,
  msToFrame,
  overlapsSameKey,
  sameTimelineItem,
  timelineItemToBlock,
  toTimeMs,
} from "./traceModel";

function block(overrides: Partial<TraceBlock>): TraceBlock {
  return {
    id: "b1",
    key: "keyboard.e",
    press: 60,
    release: 75,
    ...overrides,
  };
}

describe("traceModel 帧换算", () => {
  it("帧与毫秒往返保持整数帧", () => {
    for (const frame of [1, 15, 60, 360, 18000, TRACE_MAX_FRAME]) {
      expect(msToFrame(frameToMs(frame))).toBe(frame);
    }
  });

  it("帧号最小为 1", () => {
    expect(msToFrame(0)).toBe(1);
    expect(msToFrame(-100)).toBe(1);
  });

  it("时间值兼容 Date、数值、字符串与 valueOf 对象", () => {
    expect(toTimeMs(frameToMs(60))).toBeCloseTo(frameToMs(60), 10);
    expect(toTimeMs(new Date(frameToMs(60)))).toBeCloseTo(frameToMs(60), 10);
    expect(toTimeMs(new Date(frameToMs(60)).toISOString())).toBeCloseTo(frameToMs(60), 6);
    expect(toTimeMs({ valueOf: () => frameToMs(60) })).toBeCloseTo(frameToMs(60), 10);
    expect(toTimeMs(null)).toBeNull();
    expect(dateToFrame(frameToMs(60))).toBe(60);
    expect(dateToFrame(new Date(frameToMs(60)))).toBe(60);
  });

  it("秒标签格式", () => {
    expect(formatTraceSeconds(60)).toBe("1.0s");
    expect(formatSecondsLabel(0.1)).toBe("0.1s");
    expect(formatSecondsLabel(1)).toBe("1s");
    expect(formatSecondsLabel(90)).toBe("1m30s");
    expect(formatSecondsLabel(300)).toBe("5m");
  });
});

describe("traceModel 事件块转换", () => {
  it("按下/松开配对成一个块", () => {
    const blocks = buildBlocks([
      { frame: 60, events: [{ key: "keyboard.e", phase: "press" }] },
      { frame: 75, events: [{ key: "keyboard.e", phase: "release" }] },
    ]);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ key: "keyboard.e", press: 60, release: 75 });
  });

  it("未闭合按下保留为 open 块", () => {
    const blocks = buildBlocks([
      { frame: 60, events: [{ key: "keyboard.e", phase: "press" }] },
    ]);
    expect(blocks[0]).toMatchObject({ press: 60, release: null });
  });

  it("无匹配按下的松开标记为 invalid", () => {
    const blocks = buildBlocks([
      { frame: 60, events: [{ key: "keyboard.e", phase: "release" }] },
    ]);
    expect(blocks[0]).toMatchObject({ press: 60, release: 60, invalid: true });
  });

  it("块转事件后按帧排序", () => {
    const items = blocksToItems([
      block({ id: "a", key: "keyboard.q", press: 90, release: 100 }),
      block({ id: "b", key: "keyboard.e", press: 60, release: 75 }),
    ]);
    expect(items.map((item) => item.frame)).toEqual([60, 75, 90, 100]);
  });

  it("open 块只输出按下事件", () => {
    const items = blocksToItems([block({ id: "a", press: 60, release: null })]);
    expect(items).toEqual([
      { frame: 60, events: [{ key: "keyboard.e", phase: "press" }] },
    ]);
  });
});

describe("traceModel 布局与同键约束", () => {
  it("重叠块分配到不同轨道", () => {
    const layout = layoutBlocks([
      block({ id: "a", key: "keyboard.e", press: 10, release: 30 }),
      block({ id: "b", key: "keyboard.q", press: 20, release: 40 }),
      block({ id: "c", key: "keyboard.1", press: 31, release: 50 }),
    ]);
    expect(layout.rows).toBe(2);
    expect(layout.rowById.get("a")).not.toBe(layout.rowById.get("b"));
    expect(layout.rowById.get("a")).toBe(layout.rowById.get("c"));
  });

  it("同键拖动不会越过相邻块", () => {
    const others = [
      block({ id: "a", key: "keyboard.e", press: 10, release: 25 }),
      block({ id: "b", key: "keyboard.e", press: 40, release: 55 }),
    ];
    expect(clampMovePress(others[0], 50, 15, others)).toBe(56);
    expect(clampTraceRelease(others[0], 10, 50, others)).toBe(39);
    expect(clampTracePress(others[1], 1, 60, others)).toBe(26);
  });

  it("open 块整体移动后仍保持未闭合", () => {
    const prev = block({ id: "a", press: 60, release: null });
    const next = clampBlockEdit(prev, 63, 64, [prev]);
    expect(next).toMatchObject({ press: 63, release: null });
  });

  it("open 块左端调整保持未闭合", () => {
    const prev = block({ id: "a", press: 60, release: null });
    const next = clampBlockEdit(prev, 50, 61, [prev]);
    expect(next).toMatchObject({ press: 50, release: null });
  });

  it("open 块右端拉长转为闭合", () => {
    const prev = block({ id: "a", press: 60, release: null });
    const next = clampBlockEdit(prev, 60, 80, [prev]);
    expect(next).toMatchObject({ press: 60, release: 80 });
  });

  it("closed 块移动保持时长并被同键边界钳制", () => {
    const a = block({ id: "a", press: 10, release: 25 });
    const b = block({ id: "b", press: 40, release: 55 });
    const next = clampBlockEdit(a, 50, 65, [a, b]);
    expect(next).toMatchObject({ press: 56, release: 71 });
  });

  it("closed 块左端调整不改变松开帧", () => {
    const a = block({ id: "a", press: 10, release: 25 });
    const b = block({ id: "b", press: 40, release: 55 });
    const next = clampBlockEdit(a, 5, 25, [a, b]);
    expect(next).toMatchObject({ press: 5, release: 25 });
  });

  it("同键重叠检测", () => {
    expect(
      overlapsSameKey(
        block({ id: "new", press: 20, release: 35 }),
        [block({ id: "a", press: 10, release: 25 })],
      ),
    ).toBe(true);
    expect(
      overlapsSameKey(
        block({ id: "new", press: 26, release: 35 }),
        [block({ id: "a", press: 10, release: 25 })],
      ),
    ).toBe(false);
  });

  it("最大帧包含尾部留白", () => {
    const blocks = [block({ id: "a", press: 400, release: 500 })];
    expect(maxFrameOf(blocks)).toBe(500);
    expect(Math.max(MIN_TIMELINE_FRAMES, maxFrameOf(blocks) + TIMELINE_TAIL_FRAMES)).toBe(530);
  });
});

describe("traceModel 时间轴条目转换", () => {
  it("支持按键生成带颜色样式的条目", () => {
    const item = blockToTimelineItem(block({ id: "a" }));
    expect(item.content).toContain("E");
    expect(item.className).toContain("trace-item");
    expect(item.className).not.toContain("trace-block-unclosed");
    expect(item.style).toContain("#3b82f6");
    expect(item.end - item.start).toBeCloseTo(15 * FRAME_MS, 10);
  });

  it("open 块以最小宽度呈现并保持未闭合", () => {
    const item = blockToTimelineItem(block({ id: "a", release: null }));
    expect(item.className).toContain("trace-block-unclosed");
    expect(item.end - item.start).toBeCloseTo(FRAME_MS, 10);

    const previous = new Map([["a", block({ id: "a", release: null })]]);
    const restored = timelineItemToBlock(item, previous);
    expect(restored).toMatchObject({ press: 60, release: null });
  });

  it("未闭合块被拉长后转为已闭合", () => {
    const previous = new Map([["a", block({ id: "a", release: null })]]);
    const restored = timelineItemToBlock(
      {
        id: "a",
        key: "keyboard.e",
        start: frameToMs(60),
        end: frameToMs(80),
      },
      previous,
    );
    expect(restored).toMatchObject({ press: 60, release: 80 });
  });

  it("不支持按键显示问号并标记", () => {
    const item = blockToTimelineItem(
      block({ id: "a", key: "keyboard.w", press: 6, release: 20 }),
    );
    expect(item.cap).toBe("?");
    expect(item.className).toContain("trace-block-unsupported");
  });

  it("相同条目比较", () => {
    const a = blockToTimelineItem(block({ id: "a" }));
    const b = blockToTimelineItem(block({ id: "a" }));
    expect(sameTimelineItem(a, b)).toBe(true);
    expect(sameTimelineItem(a, { ...b, start: b.start + 1 })).toBe(false);
  });
});

describe("traceModel 视口与幽灵块", () => {
  const viewport = {
    startFrame: 1,
    endFrame: 361,
    left: 0,
    top: 0,
    width: 640,
    height: 200,
  };

  it("客户端坐标映射到帧", () => {
    expect(frameFromViewport(viewport, 320)).toBe(181);
    expect(frameFromViewport(viewport, -10)).toBeNull();
    expect(frameFromViewport(viewport, 650)).toBeNull();
  });

  it("幽灵块按视口换算位置并检测同键冲突", () => {
    const placement = computeGhostPlacement(
      { key: "keyboard.e", x: 320, y: 100 },
      [],
      viewport,
    );
    expect(placement).not.toBeNull();
    expect(placement!.left).toBeCloseTo(320);
    expect(placement!.blocked).toBe(false);

    const blocked = computeGhostPlacement(
      { key: "keyboard.e", x: 160, y: 100 },
      [block({ id: "a", press: 90, release: 105 })],
      viewport,
    );
    expect(blocked!.blocked).toBe(true);
  });

  it("幽灵块默认时长为一按", () => {
    const placement = computeGhostPlacement(
      { key: "mouse.left", x: 320, y: 100 },
      [],
      viewport,
    );
    const pxPerFrame = viewport.width / (viewport.endFrame - viewport.startFrame);
    expect(placement!.width).toBeCloseTo(DEFAULT_TAP_FRAMES * pxPerFrame);
  });
});
