import { describe, expect, it } from "vitest";
import { compileConfigurationRegion } from "../workflow/compiler";
import { validateWorkflow } from "../workflow/validator";
import { createExampleDefinition } from "./example_workflow";

describe("example workflow", () => {
  it("示例工作流通过图校验", () => {
    const definition = createExampleDefinition();
    const errors = validateWorkflow(definition).filter((item) => item.severity === "error");
    expect(errors).toEqual([]);
  });

  it("示例工作流编译出 8 个成员且结构正确", () => {
    const result = compileConfigurationRegion(createExampleDefinition(), "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(8);

    const first = result.members[0];
    expect(first.item_id).toContain("range:scene.targets[0].level:1");
    expect(first.item_id).toContain("e-1");
    const team = first.input.team as Array<Record<string, unknown>>;
    expect(team[0].slot).toBe(1);
    expect((team[0].character as Record<string, unknown>).asset_key).toBe("character:10000014");
    const targets = (first.input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets[0].level).toBe(1);
    expect((first.input.run_options as Record<string, unknown>).max_frames).toBe(60);

    const last = result.members[result.members.length - 1];
    expect(last.item_id).toContain("range:scene.targets[0].level:10");
    expect(last.item_id).toContain("e-2");
  });
});
