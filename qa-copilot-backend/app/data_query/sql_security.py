"""基于 SQL 抽象语法树的只读查询安全校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.constants import DataSourceDatabaseType

_PARAMETER_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")

_COMMON_FORBIDDEN_FUNCTIONS = {
    "sleep",
    "benchmark",
    "get_lock",
    "load_file",
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "dblink",
}
_MYSQL_FORBIDDEN_TEXT = ("into outfile", "into dumpfile", "load data", "load_file(")
_POSTGRES_FORBIDDEN_TEXT = ("copy ", "lo_import(", "lo_export(", "dblink(")


@dataclass(frozen=True, slots=True)
class SQLValidationResult:
    valid: bool
    normalized_sql: str
    referenced_tables: list[str]
    errors: list[str]


class SQLSafetyValidator:
    """只允许单条、显式字段、白名单表的 SELECT 查询。"""

    @staticmethod
    def dialect_name(database_type: DataSourceDatabaseType) -> str:
        return "mysql" if database_type is DataSourceDatabaseType.MYSQL else "postgres"

    def validate(
        self,
        sql: str,
        database_type: DataSourceDatabaseType,
        parameters: dict[str, Any],
        allowed_tables: set[str],
        sensitive_columns: dict[str, set[str]],
        max_rows: int,
    ) -> SQLValidationResult:
        errors: list[str] = []
        dialect = self.dialect_name(database_type)
        try:
            statements = parse(sql, read=dialect)
        except ParseError as exc:
            return SQLValidationResult(False, "", [], [f"SQL 语法解析失败：{exc}"])
        if len(statements) != 1:
            return SQLValidationResult(False, "", [], ["一次只能执行一条 SQL"])
        expression = statements[0]
        if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            errors.append("只允许 SELECT 或 WITH ... SELECT 查询")

        forbidden_types = tuple(
            item
            for item in (
                getattr(exp, "Insert", None),
                getattr(exp, "Update", None),
                getattr(exp, "Delete", None),
                getattr(exp, "Create", None),
                getattr(exp, "Drop", None),
                getattr(exp, "Alter", None),
                getattr(exp, "Merge", None),
                getattr(exp, "Command", None),
                getattr(exp, "Copy", None),
                getattr(exp, "Into", None),
                getattr(exp, "Lock", None),
            )
            if item is not None
        )
        if forbidden_types and any(isinstance(node, forbidden_types) for node in expression.walk()):
            errors.append("SQL 包含修改数据或数据库结构的操作")

        lowered_sql = " ".join(sql.lower().split())
        forbidden_text = (
            _MYSQL_FORBIDDEN_TEXT
            if database_type is DataSourceDatabaseType.MYSQL
            else _POSTGRES_FORBIDDEN_TEXT
        )
        if any(value in lowered_sql for value in forbidden_text):
            errors.append("SQL 包含当前数据库禁止的文件、跨库或高风险能力")

        for function in expression.find_all(exp.Func):
            function_name = str(getattr(function, "name", "") or getattr(function, "key", "")).lower()
            if function_name in _COMMON_FORBIDDEN_FUNCTIONS:
                errors.append(f"禁止调用高风险数据库函数：{function_name}")

        for select_expression in expression.find_all(exp.Select):
            for projection in select_expression.expressions:
                if getattr(projection, "is_star", False):
                    errors.append("禁止 SELECT *，必须明确选择需要返回的字段")

        cte_names = {str(item.alias_or_name).lower() for item in expression.find_all(exp.CTE)}
        referenced_tables: list[str] = []
        normalized_allowed = {value.lower() for value in allowed_tables}
        table_aliases: dict[str, str] = {}
        for table in expression.find_all(exp.Table):
            table_name = str(table.name)
            if table_name.lower() in cte_names:
                continue
            qualified = ".".join(part for part in (str(table.db or ""), table_name) if part)
            table_aliases[str(table.alias_or_name).lower()] = table_name.lower()
            referenced_tables.append(qualified or table_name)
            if (
                normalized_allowed
                and table_name.lower() not in normalized_allowed
                and qualified.lower() not in normalized_allowed
            ):
                errors.append(f"表不在数据源查询白名单中：{qualified or table_name}")

        normalized_sensitive = {
            table.lower(): {column.lower() for column in columns} for table, columns in sensitive_columns.items()
        }
        all_sensitive = set().union(*normalized_sensitive.values()) if normalized_sensitive else set()
        for column in expression.find_all(exp.Column):
            column_name = str(column.name).lower()
            table_name = str(column.table or "").lower()
            resolved_table = table_aliases.get(table_name, table_name)
            if resolved_table and column_name in normalized_sensitive.get(resolved_table, set()):
                errors.append(f"禁止查询敏感字段：{resolved_table}.{column_name}")
            elif not table_name and column_name in all_sensitive:
                errors.append(f"敏感字段必须被拒绝：{column_name}")

        placeholders = set(_PARAMETER_PATTERN.findall(sql))
        missing_parameters = sorted(placeholders.difference(parameters))
        if missing_parameters:
            errors.append("缺少 SQL 绑定参数：" + ", ".join(missing_parameters))

        if errors:
            return SQLValidationResult(False, "", sorted(set(referenced_tables)), list(dict.fromkeys(errors)))

        expression.limit(max_rows + 1, copy=False)
        normalized_sql = expression.sql(dialect=dialect, pretty=True)
        return SQLValidationResult(True, normalized_sql, sorted(set(referenced_tables)), [])
