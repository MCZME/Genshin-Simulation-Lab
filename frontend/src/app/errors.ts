/** App 与编排 hook 共享的错误工具。 */

export function toMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

/** fetch 中断与轮询取消都以 AbortError 抛出；批次步骤按取消而非失败呈现。 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
