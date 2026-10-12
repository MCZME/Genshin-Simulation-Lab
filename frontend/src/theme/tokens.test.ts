import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  COLORS,
  FONT,
  RADIUS,
  SHADOW,
  SPACING,
  TYPOGRAPHY,
  Z_INDEX,
} from "./tokens";

/** camelCase -> kebab-case，与 tokens.css 的属性名一一对应。 */
function kebab(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

/** 展平嵌套字符串记录为 --prefix-key: value。 */
function flattenStrings(
  source: Record<string, unknown>,
  prefix: string,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(source)) {
    const name = `${prefix}-${kebab(key)}`;
    if (typeof value === "string") {
      out[name] = value;
    } else if (value !== null && typeof value === "object") {
      Object.assign(
        out,
        flattenStrings(value as Record<string, unknown>, name),
      );
    }
  }
  return out;
}

/** 数值记录转为带 px 单位的 --prefix-key（非数值条目忽略，由其它断言覆盖）。 */
function withPx(
  source: Record<string, unknown>,
  prefix: string,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(source)) {
    if (typeof value === "number") {
      out[`${prefix}-${kebab(key)}`] = `${value}px`;
    }
  }
  return out;
}

/** 无单位数值记录转为 --prefix-key（行高、z-index 用）。 */
function withUnitless(
  source: Record<string, unknown>,
  prefix: string,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(source)) {
    if (typeof value === "number") {
      out[`${prefix}-${kebab(key)}`] = String(value);
    }
  }
  return out;
}

/** tokens.ts 期望导出的全部 CSS 自定义属性（分组前缀与 tokens.css 段落一致）。 */
function expectedVars(): Record<string, string> {
  const { region, nodeCategory, severity, element, status, ...surface } = COLORS;
  return {
    ...flattenStrings(surface, "--color"),
    ...flattenStrings(nodeCategory, "--color-node"),
    ...flattenStrings(region, "--color-region"),
    ...flattenStrings(severity, "--color-severity"),
    ...flattenStrings(element, "--color-element"),
    ...flattenStrings(status, "--color-status"),
    ...withPx(SPACING as unknown as Record<string, unknown>, "--space"),
    ...withPx(TYPOGRAPHY as unknown as Record<string, unknown>, "--font-size"),
    ...withUnitless(
      TYPOGRAPHY.lineHeight as unknown as Record<string, unknown>,
      "--line-height",
    ),
    ...withPx(RADIUS as unknown as Record<string, unknown>, "--radius"),
    ...flattenStrings(SHADOW as unknown as Record<string, unknown>, "--shadow"),
    ...withUnitless(Z_INDEX as unknown as Record<string, unknown>, "--z"),
    ...flattenStrings(FONT as unknown as Record<string, unknown>, "--font"),
  };
}

function parseCssVars(source: string): Record<string, string> {
  const parsed: Record<string, string> = {};
  for (const line of source.split("\n")) {
    const match = /^\s*--([\w-]+):\s*(.+?);\s*$/.exec(line);
    const value = match?.[2];
    if (match !== null && value !== undefined) {
      parsed[`--${match[1]}`] = value;
    }
  }
  return parsed;
}

describe("设计令牌", () => {
  const parsed = parseCssVars(
    readFileSync(new URL("./tokens.css", import.meta.url), "utf8"),
  );
  const expected = expectedVars();

  it("tokens.css 与 tokens.ts 完全一致（无缺失、无多余、无漂移）", () => {
    expect(Object.keys(parsed).sort()).toEqual(Object.keys(expected).sort());
    for (const [name, value] of Object.entries(expected)) {
      expect(parsed[name], name).toBe(value);
    }
  });

  it("身份色与过程色不共享精确色值", () => {
    const identity: string[] = [
      ...Object.values(COLORS.nodeCategory),
      ...Object.values(COLORS.region),
      ...Object.values(COLORS.element),
      COLORS.fallback,
    ];
    const process: string[] = [
      ...Object.values(COLORS.severity),
      ...Object.values(COLORS.status),
      COLORS.selection,
    ];
    const collisions = identity.filter((value) => process.includes(value));
    expect(collisions).toEqual([]);
  });

  it("严重度语义保持红=失败、琥珀=警告、蓝=提示", () => {
    expect(COLORS.severity.error).toBe("#ef4444");
    expect(COLORS.severity.warning).toBe("#f59e0b");
    expect(COLORS.severity.info).toBe("#3b82f6");
  });

  it("字号阶梯下限为 11px，禁止 9/10px 字号令牌", () => {
    const sizes: number[] = [];
    for (const value of Object.values(TYPOGRAPHY)) {
      if (typeof value === "number") {
        sizes.push(value);
      }
    }
    expect(Math.min(...sizes)).toBe(11);
  });
});
