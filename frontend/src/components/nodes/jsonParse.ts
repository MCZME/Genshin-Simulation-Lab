/**
 * 详情类组件对后端无类型 JSON（summary/audit/帧状态载荷）的防御式解析共享工具。
 * 三处实现曾各自复制并出现签名漂移，统一收敛到此处；取值口径为最宽签名，
 * 调用方传非空记录同样适用。
 */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readString(
  record: Record<string, unknown> | null,
  key: string,
): string | null {
  if (record === null) {
    return null;
  }
  const value = record[key];
  return typeof value === "string" && value !== "" ? value : null;
}

export function readNumber(
  record: Record<string, unknown> | null,
  key: string,
): number | null {
  if (record === null) {
    return null;
  }
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function readBoolean(record: Record<string, unknown>, key: string): boolean {
  return record[key] === true;
}

export function readRecord(record: unknown, key: string): Record<string, unknown> | null {
  if (!isRecord(record)) {
    return null;
  }
  const value = record[key];
  return isRecord(value) ? value : null;
}

export function readRecordList(record: unknown, key: string): Record<string, unknown>[] {
  const value = isRecord(record) ? record[key] : undefined;
  return Array.isArray(value) ? value.filter(isRecord) : [];
}
