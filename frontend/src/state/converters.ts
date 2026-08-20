import type { WorkflowDefinition } from "../workflow/types";
import type { EditorState } from "./editor_state";

export function definitionToEditorState(definition: WorkflowDefinition): EditorState {
  const saved = deepClone(definition);
  return {
    definition: saved,
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
    past: [],
    future: [],
    saved,
  };
}

export function editorStateToDefinition(state: EditorState): WorkflowDefinition {
  return deepClone(state.definition);
}

export function cloneEditorState(state: EditorState): EditorState {
  return {
    definition: deepClone(state.definition),
    selection: {
      regions: [...state.selection.regions],
      nodes: [...state.selection.nodes],
      edges: [...state.selection.edges],
    },
    dirty: state.dirty,
    past: state.past.map((definition) => deepClone(definition)),
    future: state.future.map((definition) => deepClone(definition)),
    saved: state.saved === null ? null : deepClone(state.saved),
  };
}

function deepClone<T>(value: T): T {
  return structuredClone(value);
}
