"""分析模板用例：模板目录与执行。

模板声明与 SQL 由 infrastructure/results_sqlite/templates.py 拥有；
本服务只做声明级校验（模板存在、参数类型与必填、关系形状），
再委托执行器返回结果表，不接触数据库实现。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from genshin_sim.application.models import (
    RelationTable,
    TemplateDeclaration,
    TemplateResult,
)
from genshin_sim.application.services.protocols import AnalysisTemplateExecutor

logger = logging.getLogger(__name__)

MAX_RELATION_ROWS = 5_000


class TemplateNotFoundError(LookupError):
    """请求的模板不存在。"""


class TemplateValidationError(ValueError):
    """模板参数或关系输入不合法。"""


class AnalysisTemplatesService:
    """模板目录与执行的用例门面。"""

    def __init__(self, executor: AnalysisTemplateExecutor) -> None:
        self._executor = executor

    def list_templates(self) -> tuple[TemplateDeclaration, ...]:
        return self._executor.list_templates()

    def execute(
        self,
        template_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        relations: Mapping[str, RelationTable] | None = None,
    ) -> TemplateResult:
        """校验声明后执行模板，返回一张结果表。"""

        declarations = {
            declaration.template_id: declaration for declaration in self._executor.list_templates()
        }
        declaration = declarations.get(template_id)
        if declaration is None:
            raise TemplateNotFoundError(template_id)

        validated_params = _validate_params(declaration, params)
        validated_relations = _validate_relations(declaration, relations)
        logger.debug(
            "执行分析模板",
            extra={
                "template_id": template_id,
                "params": validated_params,
                "relation_names": tuple(validated_relations),
            },
        )
        return self._executor.execute(template_id, validated_params, validated_relations)


def _validate_params(
    declaration: TemplateDeclaration,
    params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """校验参数存在性、必填与类型；未知参数拒绝。"""

    supplied = dict(params or {})
    declared = {param.name: param for param in declaration.params}
    for name in supplied:
        if name not in declared:
            raise TemplateValidationError(f"模板 {declaration.template_id} 不支持参数：{name}")
    for param in declaration.params:
        if param.required and param.name not in supplied:
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 缺少必填参数：{param.name}"
            )
        if param.name in supplied and not _type_matches(param.type, supplied[param.name]):
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 参数 {param.name} 类型不符：需要 {param.type}"
            )
    return supplied


def _validate_relations(
    declaration: TemplateDeclaration,
    relations: Mapping[str, RelationTable] | None,
) -> dict[str, RelationTable]:
    """校验关系输入：名称在声明内、必填齐全、所需列存在、行数上限。"""

    supplied = dict(relations or {})
    declared = {relation.name: relation for relation in declaration.relations}
    for name in supplied:
        if name not in declared:
            raise TemplateValidationError(f"模板 {declaration.template_id} 不支持关系输入：{name}")
    for relation in declaration.relations:
        if relation.required and relation.name not in supplied:
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 缺少必填关系输入：{relation.name}"
            )
    for name, table in supplied.items():
        spec = declared[name]
        column_index = {column: idx for idx, column in enumerate(table.columns)}
        missing = [column for column in spec.columns if column not in column_index]
        if missing:
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 关系输入 {name} 缺少所需列：{missing}"
            )
        if len(table.rows) > MAX_RELATION_ROWS:
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 关系输入 {name} 行数超过上限 {MAX_RELATION_ROWS}"
            )
        if any(len(row) != len(table.columns) for row in table.rows):
            raise TemplateValidationError(
                f"模板 {declaration.template_id} 关系输入 {name} 行宽与列不一致"
            )
    return supplied


def _type_matches(type_name: str, value: Any) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "string[]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "bool":
        return isinstance(value, bool)
    return True
