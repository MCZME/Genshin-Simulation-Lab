// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NumberField } from "./fields";

afterEach(cleanup);

describe("NumberField 数字显示与滑块编辑", () => {
  it("显示态渲染数字，点击进入滑块", () => {
    render(<NumberField value={90} min={1} max={100} onChange={vi.fn()} />);
    const display = screen.getByRole("button", { name: "90" });
    fireEvent.click(display);
    expect(screen.getByRole("slider")).toBeTruthy();
  });

  it("连续整数范围滑块按索引映射并提交", () => {
    const onChange = vi.fn();
    render(<NumberField value={1} min={1} max={4} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("min")).toBe("0");
    expect(slider.getAttribute("max")).toBe("3");
    expect(slider.className).toContain("nodrag");
    fireEvent.change(slider, { target: { value: "3" } });
    expect(screen.getByText("4")).toBeTruthy();
    fireEvent.blur(slider);
    expect(onChange).toHaveBeenCalledWith(4);
  });

  it("离散选项按索引映射（角色等级 95）", () => {
    const onChange = vi.fn();
    const options = [...Array.from({ length: 90 }, (_, index) => index + 1), 95, 100];
    render(<NumberField value={90} options={options} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "90" }));
    const slider = screen.getByRole("slider");
    expect(slider.getAttribute("max")).toBe("91");
    fireEvent.change(slider, { target: { value: "90" } });
    expect(screen.getByText("95")).toBeTruthy();
    fireEvent.blur(slider);
    expect(onChange).toHaveBeenCalledWith(95);
  });

  it("无界数字字段编辑态保留输入框", () => {
    const onChange = vi.fn();
    render(<NumberField value={18000} min={1} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "18000" }));
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "20000" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith(20000);
  });

  it("Esc 取消编辑不提交", () => {
    const onChange = vi.fn();
    render(<NumberField value={2} min={1} max={4} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "3" } });
    fireEvent.keyDown(slider, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "2" })).toBeTruthy();
  });

  it("Enter 提交并退出编辑", () => {
    const onChange = vi.fn();
    render(<NumberField value={1} min={1} max={4} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    const slider = screen.getByRole("slider");
    fireEvent.change(slider, { target: { value: "2" } });
    fireEvent.keyDown(slider, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(3);
    expect(screen.getByRole("button", { name: "1" })).toBeTruthy();
  });

  it("未设置时显示占位", () => {
    render(<NumberField value={null} min={1} max={4} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "未设置" })).toBeTruthy();
  });
});
