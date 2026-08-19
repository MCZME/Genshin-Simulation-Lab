import { describe, expect, it } from "vitest";
import { parsePath, setPath } from "./path";

describe("parsePath", () => {
  it("解析标识符与数组索引", () => {
    expect(parsePath("team[0].character")).toEqual(["team", 0, "character"]);
    expect(parsePath("scene.targets[0].level")).toEqual(["scene", "targets", 0, "level"]);
    expect(parsePath("run_options.max_frames")).toEqual(["run_options", "max_frames"]);
  });

  it("非法路径抛错", () => {
    expect(() => parsePath("")).toThrow();
    expect(() => parsePath("team[0")).toThrow();
    expect(() => parsePath("a..b")).toThrow();
    expect(() => parsePath("0team")).toThrow();
  });
});

describe("setPath", () => {
  it("按路径创建嵌套对象与数组", () => {
    const document: Record<string, unknown> = {};
    setPath(document, "team[0].character", { asset_key: "character:barbara" });
    setPath(document, "team[0].weapon", { asset_key: "weapon:11512" });
    expect(document).toEqual({
      team: [{ character: { asset_key: "character:barbara" }, weapon: { asset_key: "weapon:11512" } }],
    });
  });

  it("保留既有数组槽位并返回是否覆盖", () => {
    const document: Record<string, unknown> = {};
    expect(setPath(document, "team[0].character", { asset_key: "a" })).toBe(false);
    expect(setPath(document, "team[1].weapon", { asset_key: "b" })).toBe(false);
    expect((document.team as unknown[]).length).toBe(2);
    expect(setPath(document, "team[0].character", { asset_key: "c" })).toBe(true);
  });
});
