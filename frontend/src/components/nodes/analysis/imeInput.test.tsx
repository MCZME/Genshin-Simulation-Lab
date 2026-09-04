// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImeSafeInput } from "./imeInput";

afterEach(() => {
  cleanup();
});

describe("ImeSafeInput", () => {
  it("普通输入即时写回", () => {
    const onChange = vi.fn();
    render(<ImeSafeInput value="" onChange={onChange} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "dps" } });
    expect(onChange).toHaveBeenLastCalledWith("dps");
  });

  it("输入法组合期间镜像草稿且不写回，组合结束写回最终值", () => {
    const onChange = vi.fn();
    render(<ImeSafeInput value="" onChange={onChange} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;

    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "jues" } });
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: "角色" } });
    fireEvent.compositionEnd(input);
    expect(onChange).toHaveBeenLastCalledWith("角色");
  });

  it("组合期间受控值镜像 DOM，父组件重渲染不打断组合", () => {
    const onChange = vi.fn();
    const { rerender } = render(<ImeSafeInput value="旧值" onChange={onChange} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;

    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "dian" } });
    rerender(<ImeSafeInput value="旧值" onChange={onChange} />);
    expect(input.value).toBe("dian");
  });
});
