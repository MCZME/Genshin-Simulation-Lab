import type { EnumValue } from "../../workflow/types";
import { AssetPicker } from "../common/AssetPicker";
import {
  CollapsibleGroup,
  FieldRow,
  InlineError,
  NumberField,
  SelectField,
  TextField,
} from "../common/fields";
import type { NodeEditorProps } from "./common";
import { asNumber, asString, firstError, firstErrorPrefix, isPlainObject } from "./common";
import {
  defaultPathParamValues,
  dimensionPresentation,
  getScanDimension,
  resolveScanPath,
  scanDimensionOptions,
  toDisplayValue,
  toStoredValue,
  type ScanDimensionSpec,
} from "../../workflow/scanDimensions";

const ENUM_VALUE_TYPES = [
  { value: "asset", label: "资产" },
  { value: "number", label: "数值" },
  { value: "string", label: "文本" },
  { value: "json_fragment", label: "JSON 片段" },
] as const;

const SLOT_OPTIONS = [1, 2, 3, 4].map((slot) => ({
  value: String(slot),
  label: `槽位 ${slot}`,
}));

type ScanMode = "dimension" | "custom";

/** 维度模式下节点参数的解析结果。 */
interface VariantEditState {
  mode: ScanMode;
  spec: ScanDimensionSpec | null;
  pathParams: Record<string, unknown>;
  /** 维度模式为推导路径，自定义模式为节点参数 path。 */
  resolvedPath: string;
}

function readVariantState(params: Record<string, unknown>): VariantEditState {
  const dimensionKey = typeof params.dimension === "string" ? params.dimension : null;
  const pathParams = isPlainObject(params.path_params) ? params.path_params : {};
  if (dimensionKey === null) {
    return {
      mode: "custom",
      spec: null,
      pathParams,
      resolvedPath: asString(params.path) ?? "",
    };
  }
  const spec = getScanDimension(dimensionKey);
  return {
    mode: "dimension",
    spec,
    pathParams,
    resolvedPath: spec === null ? "" : resolveScanPath(spec, pathParams),
  };
}

function ScanModeSwitch({
  value,
  onChange,
}: {
  value: ScanMode;
  onChange: (value: ScanMode) => void;
}) {
  return (
    <div className="scan-mode-switch" role="group" aria-label="配置方式">
      <button
        type="button"
        className={value === "dimension" ? "active" : ""}
        onClick={() => onChange("dimension")}
      >
        常用维度
      </button>
      <button
        type="button"
        className={value === "custom" ? "active" : ""}
        onClick={() => onChange("custom")}
      >
        自定义路径
      </button>
    </div>
  );
}

function PathParamFields({
  spec,
  pathParams,
  onUpdate,
}: {
  spec: ScanDimensionSpec;
  pathParams: Record<string, unknown>;
  onUpdate: (name: string, value: unknown) => void;
}) {
  return (
    <>
      {spec.pathParams.map((param) => {
        if (param.param === "slot") {
          return (
            <FieldRow key="slot" label={param.label}>
              <SelectField
                value={String(pathParams.slot ?? 1)}
                options={SLOT_OPTIONS}
                onChange={(value) => onUpdate("slot", Number(value))}
              />
            </FieldRow>
          );
        }
        if (param.param === "target_index") {
          return (
            <FieldRow key="target_index" label={param.label}>
              <NumberField
                value={asNumber(pathParams.target_index) ?? 0}
                min={0}
                onChange={(value) => onUpdate("target_index", value ?? 0)}
              />
            </FieldRow>
          );
        }
        return (
          <FieldRow key="choice" label={param.label}>
            <SelectField
              value={String(pathParams.choice ?? param.options[0]?.value ?? "")}
              options={[...param.options]}
              onChange={(value) => onUpdate("choice", value)}
            />
          </FieldRow>
        );
      })}
    </>
  );
}

function ScanPathHint({ path, error }: { path: string; error?: string }) {
  return (
    <div className="scan-path-hint">
      <code className="scan-path-value">{path}</code>
      {error !== undefined && <InlineError message={error} />}
    </div>
  );
}

/** 维度模式下新增取值的默认值。 */
function defaultEnumValue(spec: ScanDimensionSpec): string | number {
  return spec.valueType === "number" ? (spec.constraints?.min ?? 0) : "";
}

export function EnumEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const { mode, spec, pathParams, resolvedPath } = readVariantState(params);
  const values = Array.isArray(params.values) ? (params.values as EnumValue[]) : [];
  const customValueType = asString(params.value_type) ?? "asset";
  const valueType = spec !== null ? spec.valueType : customValueType;
  const presentation =
    spec !== null ? dimensionPresentation(spec, pathParams) : "raw";
  const percent = presentation === "percent";

  function updateValues(next: EnumValue[]) {
    onChange({ ...params, values: next });
  }

  function updatePathParam(name: string, value: unknown) {
    onChange({ ...params, path_params: { ...pathParams, [name]: value } });
  }

  function applyDimension(key: string) {
    const nextSpec = getScanDimension(key);
    if (nextSpec === null) {
      return;
    }
    onChange({
      ...params,
      dimension: key,
      path_params: defaultPathParamValues(nextSpec),
      values: [{ item_id: nextEnumId(values), value: defaultEnumValue(nextSpec), label: null }],
    });
  }

  function switchMode(next: ScanMode) {
    if (next === mode) {
      return;
    }
    if (next === "custom") {
      // 以当前推导路径与值类型作为自定义起点
      onChange({ ...params, dimension: null, path: resolvedPath, value_type: valueType });
      return;
    }
    const first = scanDimensionOptions("enum")[0];
    if (first !== undefined) {
      applyDimension(first.value);
    }
  }

  function setValueAt(index: number, value: string | number) {
    const next = [...values];
    next[index] = { ...(values[index] ?? { item_id: "", label: null }), value };
    updateValues(next);
  }

  function renderValueInput(item: EnumValue, index: number) {
    if (mode === "dimension" && spec !== null && spec.valueType === "asset") {
      return (
        <AssetPicker
          assetType={spec.assetType ?? "characters"}
          value={String(item.value)}
          ariaLabel="扫描取值资产"
          onChange={(value) => setValueAt(index, value)}
        />
      );
    }
    if (valueType === "number") {
      const stored = typeof item.value === "number" ? item.value : Number(item.value);
      return (
        <NumberField
          value={Number.isFinite(stored) ? toDisplayValue(presentation, stored) : null}
          min={mode === "dimension" ? spec?.constraints?.min : undefined}
          max={mode === "dimension" ? spec?.constraints?.max : undefined}
          format={percent ? (value) => `${value}%` : undefined}
          onChange={(value) =>
            setValueAt(index, toStoredValue(presentation, value ?? 0))
          }
        />
      );
    }
    return (
      <TextField
        value={String(item.value ?? "")}
        mono
        onChange={(value) => setValueAt(index, value)}
      />
    );
  }

  return (
    <div className="node-editor">
      <ScanModeSwitch value={mode} onChange={switchMode} />
      {mode === "dimension" ? (
        <>
          <FieldRow label="扫描维度" error={firstError(fieldErrors, "dimension")}>
            <SelectField
              value={typeof params.dimension === "string" ? params.dimension : ""}
              options={scanDimensionOptions("enum")}
              onChange={applyDimension}
            />
          </FieldRow>
          {spec !== null && (
            <PathParamFields spec={spec} pathParams={pathParams} onUpdate={updatePathParam} />
          )}
          <ScanPathHint
            path={resolvedPath}
            error={firstError(fieldErrors, "path_params")}
          />
        </>
      ) : (
        <>
          <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
            <TextField
              value={asString(params.path) ?? ""}
              mono
              onChange={(value) => onChange({ ...params, path: value })}
            />
          </FieldRow>
          <FieldRow label="值类型" error={firstError(fieldErrors, "value_type")}>
            <SelectField
              value={customValueType}
              options={[...ENUM_VALUE_TYPES]}
              onChange={(value) => onChange({ ...params, value_type: value })}
            />
          </FieldRow>
        </>
      )}
      <CollapsibleGroup title="取值" summary={`${values.length} 个取值`}>
        {firstErrorPrefix(fieldErrors, "values") !== undefined && (
          <InlineError message={firstErrorPrefix(fieldErrors, "values")!} />
        )}
        <div className="enum-values">
          {values.map((item, index) => (
            <div className="enum-value-row" key={item.item_id}>
              <span className="enum-item-id">{item.item_id}</span>
              {renderValueInput(item, index)}
              <TextField
                value={item.label ?? ""}
                placeholder="标签"
                onChange={(value) => {
                  const next = [...values];
                  next[index] = { ...item, label: value === "" ? null : value };
                  updateValues(next);
                }}
              />
              <button
                type="button"
                className="icon-button"
                title="删除取值"
                onClick={() => updateValues(values.filter((_, valueIndex) => valueIndex !== index))}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              updateValues([
                ...values,
                {
                  item_id: nextEnumId(values),
                  value: mode === "dimension" && spec !== null ? defaultEnumValue(spec) : valueType === "number" ? 0 : "",
                  label: null,
                },
              ])
            }
          >
            + 添加取值
          </button>
        </div>
      </CollapsibleGroup>
    </div>
  );
}

export function RangeEditor({ node, onChange, fieldErrors = {} }: NodeEditorProps) {
  const params = node.params;
  const { mode, spec, pathParams, resolvedPath } = readVariantState(params);
  const presentation =
    spec !== null ? dimensionPresentation(spec, pathParams) : "raw";
  const percent = presentation === "percent";

  function updatePathParam(name: string, value: unknown) {
    onChange({ ...params, path_params: { ...pathParams, [name]: value } });
  }

  function applyDimension(key: string) {
    const nextSpec = getScanDimension(key);
    if (nextSpec === null) {
      return;
    }
    const rangeDefault = nextSpec.constraints?.rangeDefault ?? {
      start: 1,
      end: 10,
      step: 1,
    };
    onChange({
      ...params,
      dimension: key,
      path_params: defaultPathParamValues(nextSpec),
      start: rangeDefault.start,
      end: rangeDefault.end,
      step: rangeDefault.step,
    });
  }

  function switchMode(next: ScanMode) {
    if (next === mode) {
      return;
    }
    if (next === "custom") {
      onChange({ ...params, dimension: null, path: resolvedPath });
      return;
    }
    const first = scanDimensionOptions("range")[0];
    if (first !== undefined) {
      applyDimension(first.value);
    }
  }

  /** 区间字段按显示值输入，percent 维度在显示与存储间换算。 */
  function updateRangeField(
    field: "start" | "end" | "step",
    fallbackDisplay: number,
    value: number | null,
  ) {
    onChange({
      ...params,
      [field]: toStoredValue(presentation, value ?? fallbackDisplay),
    });
  }

  function rangeFieldProps(field: "start" | "end" | "step", fallbackDisplay: number) {
    const stored = asNumber(params[field]);
    return {
      value: stored === null ? null : toDisplayValue(presentation, stored),
      min: mode === "dimension" ? spec?.constraints?.min : undefined,
      max: mode === "dimension" ? spec?.constraints?.max : undefined,
      format: percent ? ((value: number) => `${value}%`) : undefined,
      onChange: (value: number | null) => updateRangeField(field, fallbackDisplay, value),
    };
  }

  return (
    <div className="node-editor">
      <ScanModeSwitch value={mode} onChange={switchMode} />
      {mode === "dimension" ? (
        <>
          <FieldRow label="扫描维度" error={firstError(fieldErrors, "dimension")}>
            <SelectField
              value={typeof params.dimension === "string" ? params.dimension : ""}
              options={scanDimensionOptions("range")}
              onChange={applyDimension}
            />
          </FieldRow>
          {spec !== null && (
            <PathParamFields spec={spec} pathParams={pathParams} onUpdate={updatePathParam} />
          )}
          <ScanPathHint
            path={resolvedPath}
            error={firstError(fieldErrors, "path_params")}
          />
        </>
      ) : (
        <FieldRow label="路径" error={firstError(fieldErrors, "path")}>
          <TextField
            value={asString(params.path) ?? ""}
            mono
            onChange={(value) => onChange({ ...params, path: value })}
          />
        </FieldRow>
      )}
      <FieldRow label="起点" error={firstError(fieldErrors, "start")}>
        <NumberField {...rangeFieldProps("start", 0)} />
      </FieldRow>
      <FieldRow label="终点" error={firstError(fieldErrors, "end")}>
        <NumberField {...rangeFieldProps("end", 10)} />
      </FieldRow>
      <FieldRow label="步长" error={firstError(fieldErrors, "step")}>
        <NumberField {...rangeFieldProps("step", 1)} />
      </FieldRow>
      <FieldRow label="标签">
        <TextField
          value={asString(params.label) ?? ""}
          onChange={(value) => onChange({ ...params, label: value === "" ? null : value })}
        />
      </FieldRow>
    </div>
  );
}

function nextEnumId(values: EnumValue[]): string {
  const max = values.reduce((current, item) => {
    const suffix = Number(item.item_id.replace(/^[^0-9]*/, ""));
    return Number.isFinite(suffix) && suffix > current ? suffix : current;
  }, 0);
  return `e-${max + 1}`;
}
