import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** 顶层渲染兜底：捕获子树渲染异常并给出恢复入口，避免整页白屏。 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("界面渲染异常", error, info.componentStack);
  }

  render() {
    if (this.state.error === null) {
      return this.props.children;
    }
    return (
      <div className="error-boundary">
        <p>界面渲染出现异常，可尝试重新加载页面；若反复出现，请反馈该问题。</p>
        <pre>{this.state.error.message}</pre>
        <button type="button" onClick={() => window.location.reload()}>
          重新加载
        </button>
      </div>
    );
  }
}
