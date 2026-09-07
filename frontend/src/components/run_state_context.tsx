import { createContext, useContext } from "react";
import { createEmptyRunState } from "../state/run_state";
import type { RunState } from "../state/run_state";
import { isRunTerminal } from "../state/run_state";

export interface RunContextValue {
  runState: RunState;
  onCancelRun: () => void;
  /** 取消本批（决策 2.38）：仅取消参数对应的当前批次，后续批次继续。 */
  onCancelBatch: (nodeId: string) => void;
}

const defaultValue: RunContextValue = {
  runState: createEmptyRunState(),
  onCancelRun: () => undefined,
  onCancelBatch: () => undefined,
};

export const RunStateContext = createContext<RunContextValue>(defaultValue);

export function useRunState(): RunContextValue {
  return useContext(RunStateContext);
}

export { isRunTerminal };
