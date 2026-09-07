import { describe, expect, it } from "vitest";
import { cyrb53, hashValue, stableStringify } from "./fingerprint";

describe("fingerprint", () => {
  it("稳定序列化对对象键顺序不敏感", () => {
    expect(stableStringify({ a: 1, b: { c: 2, d: [1, 2] } })).toBe(
      stableStringify({ b: { d: [1, 2], c: 2 }, a: 1 }),
    );
  });

  it("数组顺序敏感", () => {
    expect(stableStringify([1, 2])).not.toBe(stableStringify([2, 1]));
  });

  it("hashValue 确定且对差异敏感", () => {
    const left = { x: [1, 2], y: "a" };
    expect(hashValue(left)).toBe(hashValue({ y: "a", x: [1, 2] }));
    expect(hashValue(left)).not.toBe(hashValue({ x: [1, 2], y: "b" }));
  });

  it("cyrb53 输出稳定", () => {
    expect(cyrb53("abc")).toBe(cyrb53("abc"));
    expect(cyrb53("abc")).not.toBe(cyrb53("abd"));
  });
});
