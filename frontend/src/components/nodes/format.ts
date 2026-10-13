/** 详情类组件共享的数值展示格式（千分位、百分比与带符号变体）。 */

export function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : Number(value.toFixed(3)).toLocaleString("en-US");
}

/** 保留两位小数（尾随 0 省略）并千分位分组。 */
export function formatNumberTwoDecimals(value: number): string {
  return Number(value.toFixed(2)).toLocaleString("en-US");
}

/** 四舍五入取整并千分位分组。 */
export function formatInteger(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export function formatSignedNumber(value: number): string {
  const formatted = formatNumber(value);
  return value >= 0 ? `+${formatted}` : formatted;
}
