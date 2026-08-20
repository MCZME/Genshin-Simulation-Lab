// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { searchAssets } from "../../api/client";
import type { AssetResponse } from "../../api/client";
import { AssetPicker } from "./AssetPicker";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    searchAssets: vi.fn(),
  };
});

const mockedSearch = vi.mocked(searchAssets);

const barbara: AssetResponse = {
  asset_key: "character:barbara",
  source_id: "barbara",
  name: "芭芭拉",
  usable: true,
  status: null,
  rarity: 4,
  element: "hydro",
  weapon_type: "catalyst",
};

const kaeya: AssetResponse = {
  asset_key: "character:kaeya",
  source_id: "kaeya",
  name: "凯亚",
  usable: true,
  status: null,
  rarity: 4,
  element: "cryo",
  weapon_type: "sword",
};

const unusable: AssetResponse = {
  asset_key: "character:unusable",
  source_id: "unusable",
  name: "不可用角色",
  usable: false,
  status: "缺少实现",
  rarity: 5,
  element: "pyro",
  weapon_type: "bow",
};

afterEach(() => {
  cleanup();
  mockedSearch.mockReset();
});

describe("AssetPicker", () => {
  it("打开下拉展示名称星级与元素，选择后触发回调并关闭", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya] });
    const onChange = vi.fn();
    const { rerender } = render(
      <AssetPicker assetType="characters" value="" onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());
    expect(screen.getAllByText("★★★★").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("水").length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getByText("芭芭拉"));
    expect(onChange).toHaveBeenCalledWith("character:barbara");
    expect(screen.queryByPlaceholderText("搜索资产")).toBeNull();

    rerender(
      <AssetPicker
        assetType="characters"
        value="character:barbara"
        onChange={onChange}
      />,
    );
    expect(screen.getByText("芭芭拉")).toBeTruthy();
    expect(screen.getByText("★4")).toBeTruthy();
    expect(screen.queryByText("水")).toBeNull();
    const trigger = screen.getByRole("button", { name: /芭芭拉/ });
    expect(trigger.style.borderColor).toBe("rgb(59, 130, 246)");
  });

  it("按元素过滤列表", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya] });
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "元素：水" }));
    expect(screen.getByText("芭芭拉")).toBeTruthy();
    expect(screen.queryByText("凯亚")).toBeNull();
  });

  it("按武器类型过滤列表", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya] });
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "类型：单手剑" }));
    expect(screen.getByText("凯亚")).toBeTruthy();
    expect(screen.queryByText("芭芭拉")).toBeNull();
  });

  it("按星级过滤并支持再次点击取消", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya, unusable] });
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("不可用角色")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "星级：5★" }));
    expect(screen.getByText("不可用角色")).toBeTruthy();
    expect(screen.queryByText("芭芭拉")).toBeNull();
    expect(screen.queryByText("凯亚")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "星级：5★" }));
    expect(screen.getByText("芭芭拉")).toBeTruthy();
    expect(screen.getByText("凯亚")).toBeTruthy();
  });

  it("选择后重置过滤条件", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya] });
    const onChange = vi.fn();
    render(<AssetPicker assetType="characters" value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "元素：水" }));
    fireEvent.click(screen.getByText("芭芭拉"));

    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("凯亚")).toBeTruthy());
    expect(screen.getByRole("button", { name: "元素：全部" }).className).toContain(
      "active",
    );
  });

  it("搜索输入防抖后按新条件请求", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara] });
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() =>
      expect(mockedSearch).toHaveBeenCalledWith("characters", ""),
    );

    const input = screen.getByPlaceholderText("搜索资产");
    fireEvent.change(input, { target: { value: "芭" } });
    expect(mockedSearch).not.toHaveBeenCalledWith("characters", "芭");
    await waitFor(() =>
      expect(mockedSearch).toHaveBeenCalledWith("characters", "芭"),
    );
  });

  it("键盘上下选择与 Enter 确认", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara, kaeya] });
    const onChange = vi.fn();
    render(<AssetPicker assetType="characters" value="" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());

    const input = screen.getByPlaceholderText("搜索资产");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("character:kaeya");
  });

  it("Esc 与点击外部关闭下拉", async () => {
    mockedSearch.mockResolvedValue({ items: [barbara] });
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());

    fireEvent.keyDown(screen.getByPlaceholderText("搜索资产"), {
      key: "Escape",
    });
    expect(screen.queryByPlaceholderText("搜索资产")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("芭芭拉")).toBeTruthy());
    fireEvent.mouseDown(document.body);
    expect(screen.queryByPlaceholderText("搜索资产")).toBeNull();
  });

  it("展示加载中与不可用状态", async () => {
    let resolve: (value: { items: AssetResponse[] }) => void = () => {};
    mockedSearch.mockReturnValue(
      new Promise((next) => {
        resolve = next;
      }),
    );
    render(<AssetPicker assetType="characters" value="" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() => expect(screen.getByText("加载中…")).toBeTruthy());

    resolve({ items: [unusable] });
    await waitFor(() => expect(screen.getByText("不可用角色")).toBeTruthy());
    expect(screen.getByText("缺少实现")).toBeTruthy();
    expect(screen.getByText("★★★★★")).toBeTruthy();
  });

  it("圣遗物不显示星级与元素标签", async () => {
    mockedSearch.mockResolvedValue({
      items: [
        {
          asset_key: "artifact_set:15032",
          source_id: "15032",
          name: "绝缘之旗印",
          usable: true,
          status: null,
          rarity: null,
          element: null,
          weapon_type: null,
        },
      ],
    });
    render(
      <AssetPicker assetType="artifact-sets" value="" onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /选择资产/ }));
    await waitFor(() =>
      expect(screen.getByText("绝缘之旗印")).toBeTruthy(),
    );
    expect(screen.queryByText(/★/)).toBeNull();
  });
});
