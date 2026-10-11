export type PathSegment = string | number;

const SEGMENT_PATTERN = /^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$/;

export function parsePath(path: string): PathSegment[] {
  if (path === "") {
    throw new Error("路径不能为空");
  }
  const segments: PathSegment[] = [];
  for (const part of path.split(".")) {
    const match = SEGMENT_PATTERN.exec(part);
    if (match === null) {
      throw new Error(`路径语法错误：${path}`);
    }
    const name = match[1];
    const indexPart = match[2];
    if (name === undefined || indexPart === undefined) {
      throw new Error(`路径语法错误：${path}`);
    }
    segments.push(name);
    for (const indexMatch of indexPart.matchAll(/\[(\d+)\]/g)) {
      const value = indexMatch[1];
      if (value !== undefined) {
        segments.push(Number(value));
      }
    }
  }
  return segments;
}

/**
 * 把 value 写入 document 的 path；返回目标叶子是否已存在（供覆盖判断）。
 */
export function setPath(
  document: Record<string, unknown>,
  path: string,
  value: unknown,
): boolean {
  const segments = parsePath(path);
  const last = segments[segments.length - 1];
  if (last === undefined) {
    throw new Error("路径不能为空");
  }
  const parent = resolveParent(document, segments);

  let existed: boolean;
  if (typeof last === "number") {
    const array = parent as unknown[];
    existed = array.length > last && array[last] !== undefined;
    array[last] = value;
  } else {
    const record = parent as Record<string, unknown>;
    existed = Object.prototype.hasOwnProperty.call(record, last) && record[last] !== undefined;
    record[last] = value;
  }
  return existed;
}

function resolveParent(
  document: Record<string, unknown>,
  segments: PathSegment[],
): Record<string, unknown> | unknown[] {
  let current: unknown = document;
  for (let index = 0; index < segments.length - 1; index += 1) {
    const segment = segments[index];
    if (segment === undefined) {
      throw new Error(`路径索引越界：${segments.join(".")}`);
    }
    const next = segments[index + 1];
    if (typeof segment === "number") {
      if (!Array.isArray(current)) {
        throw new Error(`路径索引落在非数组上：${segments.join(".")}`);
      }
      const array = current as unknown[];
      ensureLength(array, segment);
      const existing = array[segment];
      if (existing === undefined || existing === null) {
        array[segment] = typeof next === "number" ? [] : {};
      } else if (typeof existing !== "object") {
        throw new Error(`路径与既有值类型冲突：${segments.join(".")}`);
      }
      current = array[segment];
    } else {
      const record = current as Record<string, unknown>;
      const existing = record[segment];
      if (existing === undefined || existing === null) {
        record[segment] = typeof next === "number" ? [] : {};
      } else if (typeof existing !== "object") {
        throw new Error(`路径与既有值类型冲突：${segments.join(".")}`);
      }
      current = record[segment];
    }
  }
  return current as Record<string, unknown> | unknown[];
}

function ensureLength(array: unknown[], index: number): void {
  while (array.length <= index) {
    array.push(undefined);
  }
}
