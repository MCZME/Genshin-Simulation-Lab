/** 计算列公式：把数学文本解析为契约 AST（《分析系统契约》4.2），并支持反解回文本。 */

export type ComputeExpr =
  | { op: "+" | "-" | "*" | "/"; left: ComputeExpr; right: ComputeExpr }
  | { col: string }
  | { lit: number };

export interface FormulaParseResult {
  ast: ComputeExpr | null;
  error: string | null;
}

const MAX_EXPR_DEPTH = 16;
const NUMERIC_TYPES = new Set(["int", "float"]);

type Token =
  | { kind: "number"; value: number; text: string }
  | { kind: "ident"; value: string }
  | { kind: "op"; value: "+" | "-" | "*" | "/" }
  | { kind: "paren"; value: "(" | ")" };

function tokenize(input: string): { tokens: Token[]; error: string | null } {
  const tokens: Token[] = [];
  let index = 0;
  while (index < input.length) {
    const char = input[index];
    if (char === " " || char === "\t" || char === "\n" || char === "\r") {
      index += 1;
      continue;
    }
    if (/[0-9]/.test(char) || (char === "." && /[0-9]/.test(input[index + 1] ?? ""))) {
      const start = index;
      while (index < input.length && /[0-9]/.test(input[index])) {
        index += 1;
      }
      if (input[index] === ".") {
        index += 1;
        while (index < input.length && /[0-9]/.test(input[index])) {
          index += 1;
        }
      }
      const text = input.slice(start, index);
      const value = Number(text);
      if (!Number.isFinite(value)) {
        return { tokens: [], error: `无法识别的数字：${text}` };
      }
      tokens.push({ kind: "number", value, text });
      continue;
    }
    if (/[A-Za-z_]/.test(char)) {
      const start = index;
      while (index < input.length && /[A-Za-z0-9_]/.test(input[index])) {
        index += 1;
      }
      tokens.push({ kind: "ident", value: input.slice(start, index) });
      continue;
    }
    if (char === "+" || char === "-" || char === "*" || char === "/") {
      tokens.push({ kind: "op", value: char });
      index += 1;
      continue;
    }
    if (char === "(" || char === ")") {
      tokens.push({ kind: "paren", value: char });
      index += 1;
      continue;
    }
    return { tokens: [], error: `无法识别的内容：${char}` };
  }
  return { tokens, error: null };
}

export function parseFormula(
  input: string,
  types: ReadonlyMap<string, string>,
): FormulaParseResult {
  const source = input.trim();
  if (source === "") {
    return { ast: null, error: "公式不能为空" };
  }
  const { tokens, error: tokenError } = tokenize(source);
  if (tokenError !== null) {
    return { ast: null, error: tokenError };
  }
  let index = 0;
  let error: string | null = null;
  const precedence = (op: string): number => (op === "+" || op === "-" ? 1 : 2);

  const parseFactor = (depth: number): ComputeExpr | null => {
    const token = tokens[index];
    if (token === undefined) {
      error = "公式不完整（缺少数值或列）";
      return null;
    }
    if (token.kind === "number") {
      index += 1;
      return { lit: token.value };
    }
    if (token.kind === "ident") {
      index += 1;
      const type = types.get(token.value);
      if (type === undefined) {
        error = `未知列：${token.value}`;
        return null;
      }
      if (!NUMERIC_TYPES.has(type)) {
        error = `列 ${token.value} 不是数值列，不能参与计算`;
        return null;
      }
      return { col: token.value };
    }
    if (token.kind === "paren" && token.value === "(") {
      if (depth + 1 > MAX_EXPR_DEPTH) {
        error = "公式嵌套过深（最多 16 层）";
        return null;
      }
      index += 1;
      const inner = parseExpr(0, depth + 1);
      if (inner === null) {
        return null;
      }
      const close = tokens[index];
      if (close === undefined || close.kind !== "paren" || close.value !== ")") {
        error = "括号不匹配";
        return null;
      }
      index += 1;
      return inner;
    }
    if (token.kind === "op" && token.value === "-") {
      index += 1;
      const inner = parseFactor(depth);
      if (inner === null) {
        return null;
      }
      if ("lit" in inner) {
        return { lit: -inner.lit };
      }
      if (depth + 1 > MAX_EXPR_DEPTH) {
        error = "公式嵌套过深（最多 16 层）";
        return null;
      }
      return { op: "*", left: { lit: -1 }, right: inner };
    }
    error = `此处应为数值、列名或左括号，实际是：${token.value}`;
    return null;
  };

  const parseExpr = (minPrecedence: number, depth: number): ComputeExpr | null => {
    let left = parseFactor(depth);
    if (left === null) {
      return null;
    }
    for (;;) {
      const token = tokens[index];
      if (
        token === undefined ||
        token.kind !== "op" ||
        precedence(token.value) < minPrecedence
      ) {
        break;
      }
      if (depth + 1 > MAX_EXPR_DEPTH) {
        error = "公式嵌套过深（最多 16 层）";
        return null;
      }
      index += 1;
      const right = parseExpr(precedence(token.value) + 1, depth + 1);
      if (right === null) {
        return null;
      }
      left = { op: token.value, left, right };
    }
    return left;
  };

  const ast = parseExpr(0, 0);
  if (ast === null) {
    return { ast: null, error };
  }
  if (index < tokens.length) {
    const rest = tokens[index];
    return {
      ast: null,
      error: `公式结尾有多余内容：${rest.kind === "number" ? rest.text : rest.value}`,
    };
  }
  return { ast, error: null };
}

export function exprToFormula(expr: ComputeExpr | null | undefined): string {
  if (expr === null || expr === undefined) {
    return "";
  }
  const precedence = (op: string): number => (op === "+" || op === "-" ? 1 : 2);
  const format = (node: ComputeExpr, parentPrecedence: number, isRight: boolean): string => {
    if ("col" in node) {
      return node.col;
    }
    if ("lit" in node) {
      return String(node.lit);
    }
    const current = precedence(node.op);
    const wrap =
      current < parentPrecedence ||
      (isRight && current === parentPrecedence && (node.op === "-" || node.op === "/"));
    const body = `${format(node.left, current, false)} ${node.op} ${format(
      node.right,
      current,
      true,
    )}`;
    return wrap ? `(${body})` : body;
  };
  return format(expr, 0, false);
}
