import { FieldRow, InlineError, TextField } from "../common/fields";
import type { ErrorOnlyProps, NodeEditorProps } from "./common";
import { asString, firstError } from "./common";
export function RootEditor({ fieldErrors = {} }: ErrorOnlyProps) {
  return (
    <div className="node-editor">
      <p className="node-note">根数据：空模拟输入骨架（文件导入后置）</p>
      {firstError(fieldErrors, "file_path") !== undefined && (
        <InlineError message={firstError(fieldErrors, "file_path")!} />
      )}
    </div>
  );
}

export function MetaEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  return (
    <div className="node-editor">
      <FieldRow label="名称" error={firstError(fieldErrors, "name")}>
        <TextField
          value={asString(params.name) ?? ""}
          onChange={(value) => onChange({ ...params, name: value })}
        />
      </FieldRow>
      <FieldRow label="描述" error={firstError(fieldErrors, "description")}>
        <TextField
          value={asString(params.description) ?? ""}
          onChange={(value) => onChange({ ...params, description: value })}
        />
      </FieldRow>
    </div>
  );
}
