import type { WorkflowDefinition } from "../workflow/types";
import type { EditorState } from "./editor_state";

export function definitionToEditorState(definition: WorkflowDefinition): EditorState {
  return {
    definition: deepClone(definition),
    selection: { regions: [], nodes: [], edges: [] },
    dirty: false,
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
  };
}

function deepClone<T>(value: T): T {
  return structuredClone(value);
}
