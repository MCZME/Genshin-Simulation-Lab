/** IME 安全的受控文本输入。
 *
 * React 受控输入在输入法组合期间可能被旧值回写打断（组合拼音被清空或误提交）。
 * 组合期间用本地草稿镜像 DOM 实时值，不写回父状态；组合结束才提交最终值。
 */

import { useRef, useState } from "react";
import type { InputHTMLAttributes } from "react";

export interface ImeSafeInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
}

export function ImeSafeInput({ value, onChange, ...rest }: ImeSafeInputProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const composingRef = useRef(false);
  const commit = (next: string) => {
    setDraft(null);
    onChange(next);
  };
  return (
    <input
      {...rest}
      value={draft ?? value}
      onChange={(event) => {
        const next = event.target.value;
        if (composingRef.current) {
          setDraft(next);
          return;
        }
        commit(next);
      }}
      onCompositionStart={() => {
        composingRef.current = true;
      }}
      onCompositionEnd={(event) => {
        composingRef.current = false;
        commit(event.currentTarget.value);
      }}
      onBlur={() => setDraft(null)}
    />
  );
}
