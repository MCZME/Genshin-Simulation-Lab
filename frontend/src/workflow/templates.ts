/**
 * 分析模板目录：后端模板声明的前端视图与解析辅助。
 *
 * 模板是后端契约（只增不改），前端在应用启动/工作区初始化后拉取一次，
 * 处理节点的参数表单、端口与校验都从目录动态解析。
 */

export interface TemplateColumn {
  name: string;
  type: string;
}

export interface TemplateParam {
  name: string;
  type: string;
  required: boolean;
  /** 允许的来源：static / config / session_group / upstream_column */
  binding: string[];
}

export interface TemplateRelation {
  name: string;
  columns: string[];
  required: boolean;
}

export interface TemplateOutput {
  columns: TemplateColumn[];
}

export interface TemplateDeclaration {
  template_id: string;
  display_name: string;
  params: TemplateParam[];
  relations: TemplateRelation[];
  output: TemplateOutput;
}

export const PARAM_BINDING_STATIC = "static";
export const PARAM_BINDING_CONFIG = "config";
export const PARAM_BINDING_SESSION_GROUP = "session_group";
export const PARAM_BINDING_UPSTREAM_COLUMN = "upstream_column";

export class TemplateCatalog {
  private readonly templates = new Map<string, TemplateDeclaration>();

  load(items: TemplateDeclaration[]): void {
    this.templates.clear();
    for (const item of items) {
      this.templates.set(item.template_id, item);
    }
  }

  list(): TemplateDeclaration[] {
    return [...this.templates.values()];
  }

  get(templateId: string): TemplateDeclaration | null {
    return this.templates.get(templateId) ?? null;
  }

  params(templateId: string): TemplateParam[] {
    return this.get(templateId)?.params ?? [];
  }

  relations(templateId: string): TemplateRelation[] {
    return this.get(templateId)?.relations ?? [];
  }

  outputColumns(templateId: string): TemplateColumn[] {
    return this.get(templateId)?.output.columns ?? [];
  }

  paramNames(templateId: string): string[] {
    return this.params(templateId).map((param) => param.name);
  }
}

/** 模板参数的绑定类别助手。 */
export function allowsBinding(param: TemplateParam, binding: string): boolean {
  return param.binding.includes(binding);
}

export function canBindSessionGroup(param: TemplateParam): boolean {
  return allowsBinding(param, PARAM_BINDING_SESSION_GROUP);
}

export function canBindStaticOrConfig(param: TemplateParam): boolean {
  return (
    allowsBinding(param, PARAM_BINDING_STATIC) ||
    allowsBinding(param, PARAM_BINDING_CONFIG)
  );
}

export function canBindUpstreamColumn(param: TemplateParam): boolean {
  return allowsBinding(param, PARAM_BINDING_UPSTREAM_COLUMN);
}
