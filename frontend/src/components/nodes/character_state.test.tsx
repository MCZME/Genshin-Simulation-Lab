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
    expect(screen.getByText("攻击力")).toBeDefined();
    expect(screen.getByText("1,543.9")).toBeDefined();
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
