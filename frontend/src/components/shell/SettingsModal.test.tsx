// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createAppSettings } from "../../state/settings";
import { SettingsModal } from "./SettingsModal";

afterEach(cleanup);

describe("SettingsModal", () => {
  it("展示开发者模式开关并回显当前值", () => {
    render(
      <SettingsModal
        settings={{ ...createAppSettings(), developerEnabled: true }}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const toggle = screen.getByLabelText("开发者模式") as HTMLInputElement;
    expect(toggle.checked).toBe(true);
  });

  it("切换开关时向上传递新的设置", () => {
    const onChange = vi.fn();
    render(
      <SettingsModal
        settings={createAppSettings()}
        onChange={onChange}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("开发者模式"));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].developerEnabled).toBe(true);
  });

  it("提示重启后生效", () => {
    render(
      <SettingsModal settings={createAppSettings()} onChange={vi.fn()} onClose={vi.fn()} />,
    );

    expect(screen.getByText(/重启服务后生效/)).toBeTruthy();
  });
});
