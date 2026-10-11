/** 详情类组件共享的数值展示格式（千分位、百分比与带符号变体）。 */

export function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString("en-US")
    : Number(value.toFixed(3)).toLocaleString("en-US");
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
