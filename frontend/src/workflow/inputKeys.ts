/** 第一版受支持按键集合；与后端按键输入契约保持一致。 */
export interface InputKeyDef {
  key: string;
  /** 面向用户的按键含义。 */
  label: string;
  /** 键帽展示文案。 */
  cap: string;
  /** 动作类别颜色。 */
  color: string;
}

export const INPUT_KEY_DEFS: readonly InputKeyDef[] = [
  { key: "keyboard.e", label: "战技", cap: "E", color: "#3b82f6" },
  { key: "keyboard.q", label: "爆发", cap: "Q", color: "#a855f7" },
  { key: "keyboard.space", label: "跳跃", cap: "空格", color: "#14b8a6" },
  { key: "keyboard.1", label: "切人", cap: "1", color: "#22c55e" },
  { key: "keyboard.2", label: "切人", cap: "2", color: "#22c55e" },
  { key: "keyboard.3", label: "切人", cap: "3", color: "#22c55e" },
  { key: "keyboard.4", label: "切人", cap: "4", color: "#22c55e" },
  { key: "mouse.left", label: "攻击", cap: "左键", color: "#ef4444" },
  { key: "mouse.right", label: "冲刺", cap: "右键", color: "#f59e0b" },
];

export const SUPPORTED_INPUT_KEYS: readonly string[] = INPUT_KEY_DEFS.map((def) => def.key);

export function inputKeyDef(key: string): InputKeyDef | null {
  return INPUT_KEY_DEFS.find((def) => def.key === key) ?? null;
}
