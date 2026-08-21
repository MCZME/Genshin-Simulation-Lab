// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ObjectPanel } from "./ObjectPanel";

describe("ObjectPanel", () => {
  afterEach(cleanup);

  it("点击收起按钮触发 onCollapse", () => {
    const onCollapse = vi.fn();
    render(<ObjectPanel onDragStart={vi.fn()} onCollapse={onCollapse} />);

    fireEvent.click(screen.getByRole("button", { name: "收起节点面板" }));

    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});
