/** IME 安全的受控文本输入。
 *
 * React 受控输入在输入法组合期间可能被旧值回写打断（组合拼音被清空或误提交）。
 * 组合期间用本地草稿镜像 DOM 实时值，不写回父状态；组合结束才提交最终值。
 */

import { useEffect, useRef, useState } from "react";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

export interface ImeSafeInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
}

export interface ImeSafeTextareaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
}

/** 组合期间用本地草稿镜像 DOM 实时值，不写回父状态；组合结束才提交最终值。 */
function useImeSafeValue(value: string, onChange: (value: string) => void) {
  const [draft, setDraft] = useState<string | null>(null);
  const composingRef = useRef(false);
  const commit = (next: string) => {
    setDraft(null);
    onChange(next);
  };
  const handleChange = (next: string) => {
    if (composingRef.current) {
      setDraft(next);
      return;
    }
    commit(next);
  };
  return {
    displayValue: draft ?? value,
    handleChange,
    handleCompositionStart: () => {
      composingRef.current = true;
    },
    handleCompositionEnd: (next: string) => {
      composingRef.current = false;
      commit(next);
    },
    handleBlur: () => setDraft(null),
  };
}

export function ImeSafeInput({ value, onChange, ...rest }: ImeSafeInputProps) {
  const ime = useImeSafeValue(value, onChange);
  return (
    <input
      {...rest}
      value={ime.displayValue}
      onChange={(event) => {
        ime.handleChange(event.target.value);
      }}
      onCompositionStart={ime.handleCompositionStart}
      onCompositionEnd={(event) => {
        ime.handleCompositionEnd(event.currentTarget.value);
      }}
      onBlur={ime.handleBlur}
    />
  );
}

/** 多行文本输入：IME 行为与单行一致，高度随内容在 44–240px 间自适应。 */
export function ImeSafeTextarea({ value, onChange, ...rest }: ImeSafeTextareaProps) {
  const ime = useImeSafeValue(value, onChange);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    const element = textareaRef.current;
    if (element === null) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${Math.min(Math.max(element.scrollHeight, 44), 240)}px`;
  }, [ime.displayValue]);
  return (
    <textarea
      {...rest}
      ref={textareaRef}
      value={ime.displayValue}
      onChange={(event) => {
        ime.handleChange(event.target.value);
      }}
      onCompositionStart={ime.handleCompositionStart}
      onCompositionEnd={(event) => {
        ime.handleCompositionEnd(event.currentTarget.value);
      }}
      onBlur={ime.handleBlur}
    />
  );
}
