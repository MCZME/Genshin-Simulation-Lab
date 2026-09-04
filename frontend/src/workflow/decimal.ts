/**
 * 十进制区间算术：使用 BigInt 定标，避免 IEEE 754 步长累积误差。
 */

const SCALE = 12;
const SCALE_BIG = 10n ** 12n;

export interface DecimalEntry {
  value: number;
  /** 规范化后的十进制字符串，用于稳定 item_id 与标签。 */
  key: string;
}

export function toScaled(value: number | string): bigint {
  const text = String(value).trim();
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (match === null) {
    throw new Error(`非法十进制数：${text}`);
  }
  const sign = match[1] === "-" ? -1n : 1n;
  const integerPart = BigInt(match[2]);
  const fractionPart = (match[3] ?? "").padEnd(SCALE, "0").slice(0, SCALE);
  return sign * (integerPart * SCALE_BIG + BigInt(fractionPart));
}

export function toDecimalString(scaled: bigint): string {
  const sign = scaled < 0n ? "-" : "";
  const absolute = scaled < 0n ? -scaled : scaled;
  const integerPart = absolute / SCALE_BIG;
  const fraction = (absolute % SCALE_BIG)
    .toString()
    .padStart(SCALE, "0")
    .replace(/0+$/, "");
  return fraction === "" ? `${sign}${integerPart}` : `${sign}${integerPart}.${fraction}`;
}

export function toNumber(scaled: bigint): number {
  return Number(toDecimalString(scaled));
}

/**
 * 生成区间取值序列：从 start 开始，只要“下一步 ≤ end”就继续包含。
 */
export function rangeEntries(
  start: number | string,
  end: number | string,
  step: number | string,
): DecimalEntry[] {
  const startScaled = toScaled(start);
  const endScaled = toScaled(end);
  const stepScaled = toScaled(step);
  if (stepScaled <= 0n) {
    throw new Error("区间步长必须大于 0");
  }
  if (startScaled > endScaled) {
    throw new Error("区间起点不能大于终点");
  }

  const entries: DecimalEntry[] = [];
  let current = startScaled;
  for (;;) {
    entries.push({ value: toNumber(current), key: toDecimalString(current) });
    current += stepScaled;
    if (current > endScaled) {
      break;
    }
  }
  return entries;
}
