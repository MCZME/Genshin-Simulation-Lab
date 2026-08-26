import { describe, expect, it } from "vitest";
import { exprToFormula, parseFormula } from "./formula";

const types = new Map([
  ["total_damage", "float"],
  ["frames_run", "int"],
  ["dps", "float"],
  ["element", "string"],
]);

describe("计算列公式解析", () => {
  it("解析乘除优先级与括号", () => {
    const { ast, error } = parseFormula("total_damage / (frames_run / 60)", types);
    expect(error).toBeNull();
    expect(ast).toEqual({
      op: "/",
      left: { col: "total_damage" },
      right: { op: "/", left: { col: "frames_run" }, right: { lit: 60 } },
    });
  });

  it("加减优先级低于乘除", () => {
    const { ast, error } = parseFormula("1 + 2 * 3", types);
    expect(error).toBeNull();
    expect(ast).toEqual({
      op: "+",
      left: { lit: 1 },
      right: { op: "*", left: { lit: 2 }, right: { lit: 3 } },
    });
  });

  it("括号提升优先级", () => {
    const { ast, error } = parseFormula("(1 + 2) * 3", types);
    expect(error).toBeNull();
    expect(ast).toEqual({
      op: "*",
      left: { op: "+", left: { lit: 1 }, right: { lit: 2 } },
      right: { lit: 3 },
    });
  });

  it("同一优先级左结合", () => {
    const { ast, error } = parseFormula("10 - 3 - 2", types);
    expect(error).toBeNull();
    expect(ast).toEqual({
      op: "-",
      left: { op: "-", left: { lit: 10 }, right: { lit: 3 } },
      right: { lit: 2 },
    });
  });

  it("一元负号：负数字面量与负列", () => {
    expect(parseFormula("-5", types).ast).toEqual({ lit: -5 });
    expect(parseFormula("-dps", types).ast).toEqual({
      op: "*",
      left: { lit: -1 },
      right: { col: "dps" },
    });
  });

  it("未知列报错", () => {
    expect(parseFormula("unknown_col + 1", types).error).toBe("未知列：unknown_col");
  });

  it("非数值列报错", () => {
    expect(parseFormula("element + 1", types).error).toBe(
      "列 element 不是数值列，不能参与计算",
    );
  });

  it("空公式报错", () => {
    expect(parseFormula("   ", types).error).toBe("公式不能为空");
  });

  it("括号不匹配报错", () => {
    expect(parseFormula("(1 + 2", types).error).toBe("括号不匹配");
  });

  it("结尾多余内容报错", () => {
    expect(parseFormula("1 + 2 3", types).error).toContain("多余内容");
  });

  it("运算符后缺操作数报错", () => {
    expect(parseFormula("1 +", types).error).toBe("公式不完整（缺少数值或列）");
  });

  it("嵌套深度超过 16 报错", () => {
    const nested = "(".repeat(17) + "1" + ")".repeat(17);
    expect(parseFormula(nested, types).error).toBe("公式嵌套过深（最多 16 层）");
  });

  it("AST 反解回公式文本", () => {
    const { ast } = parseFormula("total_damage / (frames_run / 60)", types);
    expect(exprToFormula(ast)).toBe("total_damage / (frames_run / 60)");
  });
});
