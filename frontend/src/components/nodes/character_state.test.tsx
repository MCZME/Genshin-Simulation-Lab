// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FrameStateResponse } from "../../api/client";
import { CharacterStateSheet, locateCharacter } from "./character_state";

afterEach(() => {
  cleanup();
});

const FRAME_STATE = {
  session_id: "sess-1",
  frame: 120,
  time_seconds: 2.0,
  team: {
    active_slot: 1,
    slots: [1, 2],
    characters: [
      { slot: 1, character_key: "character:barbara", combat_entity_id: "character:slot_1" },
      { slot: 2, character_key: "character:test_a", combat_entity_id: "character:slot_2" },
    ],
  },
  characters: [
    {
      slot: 1,
      character_key: "character:barbara",
      combat_entity_id: "character:slot_1",
      active: true,
      health: { current_hp: 13480, max_hp: 15000, hp_ratio: 0.8987 },
      energy: { current_energy: 45, capacity: 60, burst_ready: false },
      attributes: {
        "stat.hp.base": { value: 10875, applied_terms: [] },
        "stat.hp.max": { value: 15000, applied_terms: [] },
        "stat.atk.base": { value: 820, applied_terms: [] },
        "stat.atk.total": {
          value: 1543.9,
          applied_terms: [
            {
              target_key: "stat.atk.total",
              stage: "percent_add",
              value: 0.466,
              provider_key: "assembly.config.artifact_stats.1",
              source_ref: { kind: "config", source_key: "config:test" },
            },
          ],
        },
        "stat.def.base": { value: 1120, applied_terms: [] },
        "stat.def.total": { value: 1200, applied_terms: [] },
        "stat.crit_rate": { value: 0.624, applied_terms: [] },
        "bonus.damage.pyro": { value: 0.466, applied_terms: [] },
      },
      buffs: [
        {
          instance_ref: { domain_key: "buff", sequence: 1 },
          definition_key: "buff.maiden_2pc",
          stack_count: 1,
          max_stacks: 1,
          expires_at_frame: 480,
          resolved_modifiers: [
            {
              template: {
                term_key: "hydro_bonus",
                target_key: "bonus.damage.hydro",
                stage: "flat_add",
              },
              value: 0.15,
            },
          ],
        },
      ],
      shields: [],
      infusion: [],
      cooldowns: [],
      content_states: [],
    },
    {
      slot: 2,
      character_key: "character:test_a",
      combat_entity_id: "character:slot_2",
      active: false,
      health: { current_hp: 9000, max_hp: 13000, hp_ratio: 0.6923 },
      energy: { current_energy: 0, capacity: 60, burst_ready: false },
      attributes: {},
      buffs: [],
      shields: [],
      infusion: [],
      cooldowns: [],
      content_states: [],
    },
  ],
  resonance: { active_keys: [] },
  moonsign: { level: "", moonsign_character_refs: [] },
  coverage: {},
} as unknown as FrameStateResponse;

describe("CharacterStateSheet", () => {
  it("展示当前生命、能量、Buff 与分组属性面板", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );

    expect(screen.getByText(/帧 120（2\.00 秒）/)).toBeDefined();
    expect(screen.getByText(/character:barbara/)).toBeDefined();
    expect(screen.getByText(/13,480 \/ 15,000/)).toBeDefined();
    expect(screen.getByText("89.9%")).toBeDefined();
    expect(screen.getByText(/45 \/ 60/)).toBeDefined();
    expect(screen.getByText("大招未就绪")).toBeDefined();

    expect(screen.getByText("buff.maiden_2pc")).toBeDefined();
    expect(screen.getByText(/剩余 360 帧（6\.00 秒）/)).toBeDefined();
    expect(screen.getByText("生命值上限")).toBeDefined();
    expect(screen.getByText("15,000")).toBeDefined();
    expect(screen.getByText("10,875").className).toContain("state-sheet-attr-base");
    expect(screen.getByText("+4,125").className).toContain("state-sheet-attr-bonus");
    expect(screen.getByText("攻击力")).toBeDefined();
    expect(screen.getByText("1,543.9")).toBeDefined();
    expect(screen.getByText("820").className).toContain("state-sheet-attr-base");
    expect(screen.getByText("+723.9").className).toContain("state-sheet-attr-bonus");
    expect(screen.getByText("防御力")).toBeDefined();
    expect(screen.getByText("1,200")).toBeDefined();
    expect(screen.getByText("1,120").className).toContain("state-sheet-attr-base");
    expect(screen.getByText("+80").className).toContain("state-sheet-attr-bonus");
    expect(screen.queryByText("基础生命值")).toBeNull();
    expect(screen.queryByText("基础攻击力")).toBeNull();
    expect(screen.queryByText("基础防御力")).toBeNull();
    expect(screen.getByText("暴击率")).toBeDefined();
    expect(screen.getByText("62.4%")).toBeDefined();
    expect(screen.getByText("火元素伤害加成")).toBeDefined();
    expect(screen.getByText("46.6%")).toBeDefined();
  });

  it("点击属性行展开词条：显示阶段与 provider 原键", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /攻击力/ }));

    expect(screen.getByText("百分比加成")).toBeDefined();
    expect(screen.getByText("assembly.config.artifact_stats.1")).toBeDefined();
    expect(screen.getByText("+46.6%")).toBeDefined();
  });

  it("无词条属性展开时提示无生效修饰词条", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /暴击率/ }));
    expect(screen.getByText("无生效修饰词条")).toBeDefined();
  });

  it("点击 Buff 展开 resolved_modifiers", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /buff\.maiden_2pc/ }));

    expect(screen.getByText(/水元素伤害加成/)).toBeDefined();
    expect(screen.getByText(/固定值加成/)).toBeDefined();
    expect(screen.getByText("+15.0%")).toBeDefined();
  });

  it("focusAttributeKey 时只展示聚焦属性", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
        focusAttributeKey="stat.crit_rate"
      />,
    );
    expect(screen.getByText("暴击率")).toBeDefined();
    expect(screen.queryByText("攻击力")).toBeNull();
    expect(screen.queryByText("火元素伤害加成")).toBeNull();
  });

  it("focusAttributeKey 聚焦基础属性时按原键展示且不重复合并行", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
        focusAttributeKey="stat.hp.base"
      />,
    );
    expect(screen.getByText("基础生命值")).toBeDefined();
    expect(screen.getByText("10,875")).toBeDefined();
    expect(screen.queryByText("生命值上限")).toBeNull();
    expect(screen.queryByText("15,000")).toBeNull();
  });

  it("属性面板每三个属性排一行", () => {
    const { container } = render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );

    const rows = container.querySelectorAll(".state-sheet-attr-row");
    expect(rows.length).toBeGreaterThan(0);
    const firstRow = rows[0];
    expect(firstRow.querySelectorAll(".state-sheet-attr-head")).toHaveLength(3);
    expect(firstRow.textContent).toContain("生命值上限");
    expect(firstRow.textContent).toContain("攻击力");
    expect(firstRow.textContent).toContain("防御力");
  });

  it("同一行三格共用展开区：换格展开时收起上一个", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /攻击力/ }));
    expect(screen.getByText("assembly.config.artifact_stats.1")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /生命值上限/ }));
    expect(screen.queryByText("assembly.config.artifact_stats.1")).toBeNull();
    expect(screen.getByText("无生效修饰词条")).toBeDefined();
  });

  it("不同网格行可各自保留一个展开", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /攻击力/ }));
    fireEvent.click(screen.getByRole("button", { name: /暴击率/ }));

    expect(screen.getByText("assembly.config.artifact_stats.1")).toBeDefined();
    expect(screen.getByText("无生效修饰词条")).toBeDefined();
  });

  it("基础与总值相同时不显示 +0 拆分", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={{
          ...FRAME_STATE.characters[0],
          attributes: {
            "stat.atk.base": { value: 820, applied_terms: [] },
            "stat.atk.total": { value: 820, applied_terms: [] },
          },
        }}
      />,
    );

    expect(screen.getByText("攻击力")).toBeDefined();
    expect(screen.getByText("820")).toBeDefined();
    expect(screen.queryByText("+0")).toBeNull();
    expect(document.querySelectorAll(".state-sheet-attr-breakdown")).toHaveLength(0);
  });

  it("缺少基础值时只显示总值", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={{
          ...FRAME_STATE.characters[0],
          attributes: {
            "stat.atk.total": { value: 1543.9, applied_terms: [] },
          },
        }}
      />,
    );

    expect(screen.getByText("攻击力")).toBeDefined();
    expect(screen.getByText("1,543.9")).toBeDefined();
    expect(document.querySelectorAll(".state-sheet-attr-breakdown")).toHaveLength(0);
  });

  it("词条值为正时带 state-sheet-value-pos（增益绿）", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={FRAME_STATE.characters[0]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /攻击力/ }));

    const value = screen.getByText("+46.6%");
    expect(value.className).toContain("state-sheet-value-pos");
  });

  it("生命条按比例分级着色：低血量时为红色", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={{
          ...FRAME_STATE.characters[1],
          health: { current_hp: 2000, max_hp: 13000, hp_ratio: 0.1538 },
        }}
      />,
    );
    const fill = document.querySelector(".state-sheet-bar-fill") as HTMLElement;
    expect(fill.style.background).toBe("rgb(248, 113, 113)");
  });

  it("能量大招就绪时能量条为金色并显示就绪提示", () => {
    render(
      <CharacterStateSheet
        frameState={FRAME_STATE}
        character={{
          ...FRAME_STATE.characters[1],
          energy: { current_energy: 60, capacity: 60, burst_ready: true },
        }}
      />,
    );
    const fill = document.querySelectorAll(".state-sheet-bar-fill")[1] as HTMLElement;
    expect(fill.style.background).toBe("rgb(251, 191, 36)");
    expect(screen.getByText("大招就绪").className).toContain("ready");
  });

  it("Buff 剩余不超过 2 秒时显示 warn 态", () => {
    const buffState = JSON.parse(JSON.stringify(FRAME_STATE)) as FrameStateResponse;
    buffState.characters[0].buffs![0].expires_at_frame = 180; // 距帧 120 仅 1 秒
    render(<CharacterStateSheet frameState={buffState} character={buffState.characters[0]} />);

    const remaining = screen.getByText(/剩余 60 帧/);
    expect(remaining.className).toContain("warn");
  });

  it("Buff 已过期时显示 expired 态", () => {
    const buffState = JSON.parse(JSON.stringify(FRAME_STATE)) as FrameStateResponse;
    buffState.characters[0].buffs![0].expires_at_frame = 60; // 早于帧 120
    render(<CharacterStateSheet frameState={buffState} character={buffState.characters[0]} />);

    const remaining = screen.getByText(/剩余 0 帧/);
    expect(remaining.className).toContain("expired");
  });
});

describe("locateCharacter", () => {
  it("无定位时返回当前场上角色", () => {
    const character = locateCharacter(FRAME_STATE, {});
    expect(character?.combat_entity_id).toBe("character:slot_1");
  });

  it("按槽位/实体定位角色", () => {
    expect(locateCharacter(FRAME_STATE, { slot: 2 })?.character_key).toBe(
      "character:test_a",
    );
    expect(locateCharacter(FRAME_STATE, { entityId: "character:slot_2" })?.slot).toBe(2);
  });

  it("定位失败返回 null", () => {
    expect(locateCharacter(FRAME_STATE, { slot: 9 })).toBeNull();
    expect(locateCharacter(FRAME_STATE, { entityId: "character:slot_9" })).toBeNull();
  });
});
