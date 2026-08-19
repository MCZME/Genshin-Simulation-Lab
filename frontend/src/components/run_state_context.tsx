import { createContext, useContext } from "react";
import { createEmptyRunState } from "../state/run_state";
import type { RunState } from "../state/run_state";
import { isRunTerminal } from "../state/run_state";

export interface RunContextValue {
  runState: RunState;
  onCancelRun: () => void;
}

const defaultValue: RunContextValue = {
  runState: createEmptyRunState(),
  onCancelRun: () => undefined,
};

export const RunStateContext = createContext<RunContextValue>(defaultValue);

export function useRunState(): RunContextValue {
  return useContext(RunStateContext);
}

export { isRunTerminal };
