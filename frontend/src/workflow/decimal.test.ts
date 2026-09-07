import { describe, expect, it } from "vitest";
import { rangeEntries, toDecimalString, toScaled } from "./decimal";

describe("rangeEntries", () => {
  it("生成 1..10/step3 为 1,4,7,10", () => {
    const entries = rangeEntries(1, 10, 3);
    expect(entries.map((entry) => entry.value)).toEqual([1, 4, 7, 10]);
    expect(entries.map((entry) => entry.key)).toEqual(["1", "4", "7", "10"]);
  });

  it("十进制步长不产生浮点累积误差", () => {
    const entries = rangeEntries(0.1, 0.3, 0.1);
    expect(entries.map((entry) => entry.value)).toEqual([0.1, 0.2, 0.3]);
    expect(entries.map((entry) => entry.key)).toEqual(["0.1", "0.2", "0.3"]);
  });

  it("start 等于 end 时只生成一个值", () => {
    expect(rangeEntries(5, 5, 1).map((entry) => entry.value)).toEqual([5]);
  });

  it("一步超过终点时只包含起点", () => {
    expect(rangeEntries(2, 2, 5).map((entry) => entry.value)).toEqual([2]);
  });

  it("支持负数", () => {
    expect(rangeEntries(-1, 1, 1).map((entry) => entry.value)).toEqual([-1, 0, 1]);
  });

  it("步长小于等于 0 或起点大于终点时报错", () => {
    expect(() => rangeEntries(1, 10, 0)).toThrow();
    expect(() => rangeEntries(10, 1, 1)).toThrow();
  });
});

describe("toDecimalString", () => {
  it("规范化整数与尾随零", () => {
    expect(toDecimalString(toScaled(10))).toBe("10");
    expect(toDecimalString(toScaled(0.3))).toBe("0.3");
    expect(toDecimalString(toScaled(-2))).toBe("-2");
  });
});
