"""MySQL 结构快照、差异 SQL、受控同步与回滚工具。"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pymysql

from app.exceptions import BadRequestException, ExternalServiceException
from app.tools.network_guard import validate_tool_hostname

_SAFE_DDL = re.compile(r"^\s*(CREATE\s+TABLE|ALTER\s+TABLE)\b", re.IGNORECASE)
_FORBIDDEN_DDL = re.compile(r"\b(DROP|TRUNCATE|DELETE|UPDATE|INSERT|REPLACE|GRANT|REVOKE)\b", re.IGNORECASE)
_SAFE_ROLLBACK_DDL = re.compile(
    r"^\s*ALTER\s+TABLE\s+`[^`]+`\s+"
    r"(DROP\s+COLUMN\s+`[^`]+`|DROP\s+INDEX\s+`[^`]+`|MODIFY\s+COLUMN\s+`[^`]+`\s+.+);?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _connect(config: dict[str, Any], credentials: dict[str, str]):
    return pymysql.connect(
        host=str(config["host"]),
        port=int(config.get("port", 3306)),
        user=str(credentials.get("username", "")),
        password=str(credentials.get("password", "")),
        database=str(config["database"]),
        charset=str(config.get("charset", "utf8mb4")),
        connect_timeout=min(max(int(config.get("timeoutSeconds", 10)), 1), 30),
        read_timeout=30,
        write_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _snapshot_sync(config: dict[str, Any], credentials: dict[str, str]) -> dict[str, Any]:
    """在阻塞线程中只读抓取表、字段、索引、主外键、默认值和注释。"""
    database = str(config["database"])
    connection = _connect(config, credentials)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME, TABLE_COMMENT, ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
                (database,),
            )
            table_rows = cursor.fetchall()
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION, COLUMN_TYPE, IS_NULLABLE, "
                "COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT, CHARACTER_SET_NAME, COLLATION_NAME "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION",
                (database,),
            )
            column_rows = cursor.fetchall()
            cursor.execute(
                "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, INDEX_TYPE "
                "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s "
                "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
                (database,),
            )
            index_rows = cursor.fetchall()
            cursor.execute(
                "SELECT tc.TABLE_NAME, tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, "
                "kcu.COLUMN_NAME, kcu.ORDINAL_POSITION, kcu.REFERENCED_TABLE_NAME, "
                "kcu.REFERENCED_COLUMN_NAME, rc.UPDATE_RULE, rc.DELETE_RULE "
                "FROM information_schema.TABLE_CONSTRAINTS tc "
                "LEFT JOIN information_schema.KEY_COLUMN_USAGE kcu "
                "ON kcu.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA "
                "AND kcu.TABLE_NAME=tc.TABLE_NAME AND kcu.CONSTRAINT_NAME=tc.CONSTRAINT_NAME "
                "LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS rc "
                "ON rc.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA AND rc.CONSTRAINT_NAME=tc.CONSTRAINT_NAME "
                "WHERE tc.TABLE_SCHEMA=%s "
                "ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION",
                (database,),
            )
            constraint_rows = cursor.fetchall()
        tables: dict[str, dict[str, Any]] = {
            row["TABLE_NAME"]: {
                "comment": row["TABLE_COMMENT"] or "",
                "engine": row["ENGINE"],
                "columns": {},
                "indexes": {},
                "constraints": {},
            }
            for row in table_rows
        }
        for row in column_rows:
            tables[row["TABLE_NAME"]]["columns"][row["COLUMN_NAME"]] = {
                "position": row["ORDINAL_POSITION"],
                "type": row["COLUMN_TYPE"],
                "nullable": row["IS_NULLABLE"] == "YES",
                "default": row["COLUMN_DEFAULT"],
                "extra": row["EXTRA"] or "",
                "comment": row["COLUMN_COMMENT"] or "",
                "charset": row["CHARACTER_SET_NAME"],
                "collation": row["COLLATION_NAME"],
            }
        for row in index_rows:
            index = tables[row["TABLE_NAME"]]["indexes"].setdefault(
                row["INDEX_NAME"],
                {"unique": row["NON_UNIQUE"] == 0, "type": row["INDEX_TYPE"], "columns": []},
            )
            index["columns"].append(row["COLUMN_NAME"])
        for row in constraint_rows:
            constraint = tables[row["TABLE_NAME"]]["constraints"].setdefault(
                row["CONSTRAINT_NAME"],
                {
                    "name": row["CONSTRAINT_NAME"],
                    "type": row["CONSTRAINT_TYPE"],
                    "columns": [],
                    "referenced_table": row["REFERENCED_TABLE_NAME"],
                    "referenced_columns": [],
                    "update_rule": row["UPDATE_RULE"],
                    "delete_rule": row["DELETE_RULE"],
                },
            )
            if row["COLUMN_NAME"] is not None:
                constraint["columns"].append(row["COLUMN_NAME"])
            if row["REFERENCED_COLUMN_NAME"] is not None:
                constraint["referenced_columns"].append(row["REFERENCED_COLUMN_NAME"])
        return {"database": database, "tables": tables}
    finally:
        connection.close()


async def capture_mysql_snapshot(config: dict[str, Any], credentials: dict[str, str]) -> dict[str, Any]:
    """异步入口：把 PyMySQL 阻塞访问交给线程，避免卡住 FastAPI 事件循环。"""
    try:
        await validate_tool_hostname(str(config["host"]), int(config.get("port", 3306)))
        return await asyncio.to_thread(_snapshot_sync, config, credentials)
    except Exception as exc:
        raise ExternalServiceException(f"MySQL 结构快照失败：{type(exc).__name__}") from exc


def _quote_identifier(value: str) -> str:
    """按 MySQL 规则转义来自 information_schema 的标识符。"""
    return f"`{value.replace('`', '``')}`"


def _column_definition(name: str, column: dict[str, Any]) -> str:
    """把字段快照还原为可人工复核的 CREATE/ALTER 字段片段。"""
    parts = [_quote_identifier(name), str(column["type"]), "NULL" if column["nullable"] else "NOT NULL"]
    default = column.get("default")
    if default is not None:
        default_text = str(default)
        if re.fullmatch(r"(?i)(CURRENT_TIMESTAMP(?:\(\d+\))?|NULL|-?\d+(?:\.\d+)?)", default_text):
            parts.extend(("DEFAULT", default_text))
        else:
            parts.extend(("DEFAULT", "'" + default_text.replace("'", "''") + "'"))
    if column.get("extra"):
        parts.append(str(column["extra"]))
    if column.get("comment"):
        parts.extend(("COMMENT", "'" + str(column["comment"]).replace("'", "''") + "'"))
    return " ".join(parts)


def build_create_table_sql(table_name: str, table: dict[str, Any]) -> str:
    """从只读快照生成包含字段、索引和外键的完整建表建议。"""
    definitions = [
        _column_definition(column_name, column)
        for column_name, column in sorted(table["columns"].items(), key=lambda item: item[1]["position"])
    ]
    for index_name, index in sorted(table.get("indexes", {}).items()):
        columns = ", ".join(_quote_identifier(value) for value in index["columns"])
        if index_name == "PRIMARY":
            definitions.append(f"PRIMARY KEY ({columns})")
        else:
            unique = "UNIQUE " if index["unique"] else ""
            definitions.append(f"{unique}KEY {_quote_identifier(index_name)} ({columns})")
    for constraint in table.get("constraints", {}).values():
        if constraint["type"] != "FOREIGN KEY":
            continue
        columns = ", ".join(_quote_identifier(value) for value in constraint["columns"])
        referenced_columns = ", ".join(_quote_identifier(value) for value in constraint["referenced_columns"])
        foreign_key = (
            f"CONSTRAINT {_quote_identifier(constraint['name'])} FOREIGN KEY ({columns}) "
            f"REFERENCES {_quote_identifier(constraint['referenced_table'])} ({referenced_columns})"
        )
        if constraint.get("update_rule"):
            foreign_key += f" ON UPDATE {constraint['update_rule']}"
        if constraint.get("delete_rule"):
            foreign_key += f" ON DELETE {constraint['delete_rule']}"
        definitions.append(foreign_key)
    engine = str(table.get("engine") or "InnoDB")
    comment = str(table.get("comment") or "").replace("'", "''")
    body = ",\n  ".join(definitions)
    return f"CREATE TABLE {_quote_identifier(table_name)} (\n  {body}\n) ENGINE={engine} COMMENT='{comment}';"


def compare_mysql_snapshots(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """确定性比较两个 Schema，生成差异、迁移 SQL 和危险警告。"""
    changes: list[dict[str, Any]] = []
    sql_statements: list[str] = []
    # 回滚语句采用倒序保存：最后执行的变更必须最先撤销。
    rollback_sql_statements: list[str] = []
    warnings: list[str] = []
    source_tables = source["tables"]
    target_tables = target["tables"]
    for table_name in sorted(source_tables.keys() - target_tables.keys()):
        sql = build_create_table_sql(table_name, source_tables[table_name])
        changes.append({"type": "TABLE_MISSING", "table": table_name, "sql": sql})
        sql_statements.append(sql)
        warnings.append(f"目标端缺少表 {table_name}；将创建完整表结构，执行前必须人工复核")
    for table_name in sorted(target_tables.keys() - source_tables.keys()):
        changes.append({"type": "TARGET_EXTRA_TABLE", "table": table_name})
        warnings.append(f"目标端多出表 {table_name}；系统默认禁止生成 DROP TABLE")
    for table_name in sorted(source_tables.keys() & target_tables.keys()):
        source_columns = source_tables[table_name]["columns"]
        target_columns = target_tables[table_name]["columns"]
        for column_name in sorted(source_columns.keys() - target_columns.keys()):
            column = source_columns[column_name]
            sql = f"ALTER TABLE {_quote_identifier(table_name)} ADD COLUMN {_column_definition(column_name, column)};"
            changes.append({"type": "COLUMN_MISSING", "table": table_name, "column": column_name, "sql": sql})
            sql_statements.append(sql)
            rollback_sql_statements.insert(0, f"ALTER TABLE `{table_name}` DROP COLUMN `{column_name}`;")
        for column_name in sorted(source_columns.keys() & target_columns.keys()):
            source_column = source_columns[column_name]
            target_column = target_columns[column_name]
            if source_column != target_column:
                nullable_sql = "NULL" if source_column["nullable"] else "NOT NULL"
                sql = (
                    f"ALTER TABLE `{table_name}` MODIFY COLUMN `{column_name}` {source_column['type']} {nullable_sql};"
                )
                changes.append(
                    {
                        "type": "COLUMN_CHANGED",
                        "table": table_name,
                        "column": column_name,
                        "source": source_column,
                        "target": target_column,
                        "sql": sql,
                    }
                )
                sql_statements.append(sql)
                target_nullable = "NULL" if target_column["nullable"] else "NOT NULL"
                rollback_sql_statements.insert(
                    0,
                    f"ALTER TABLE `{table_name}` MODIFY COLUMN `{column_name}` "
                    f"{target_column['type']} {target_nullable};",
                )
                warnings.append(f"{table_name}.{column_name} 类型或约束变化，可能发生数据截断，必须人工复核")

        # 最小快照或历史快照可能没有索引键；此时按无索引处理。
        source_indexes = source_tables[table_name].get("indexes", {})
        target_indexes = target_tables[table_name].get("indexes", {})
        for index_name in sorted(source_indexes.keys() - target_indexes.keys()):
            if index_name == "PRIMARY":
                warnings.append(f"{table_name} 缺少主键；主键变更必须人工处理")
                continue
            index = source_indexes[index_name]
            unique = "UNIQUE " if index["unique"] else ""
            columns = ", ".join(f"`{column}`" for column in index["columns"])
            sql = f"ALTER TABLE `{table_name}` ADD {unique}INDEX `{index_name}` ({columns});"
            changes.append(
                {
                    "type": "INDEX_MISSING",
                    "table": table_name,
                    "index": index_name,
                    "sql": sql,
                }
            )
            sql_statements.append(sql)
            rollback_sql_statements.insert(0, f"ALTER TABLE `{table_name}` DROP INDEX `{index_name}`;")
        for index_name in sorted(target_indexes.keys() - source_indexes.keys()):
            changes.append(
                {
                    "type": "TARGET_EXTRA_INDEX",
                    "table": table_name,
                    "index": index_name,
                }
            )
            warnings.append(f"目标端 {table_name}.{index_name} 为额外索引；系统默认不自动删除")
    return {
        "source_database": source["database"],
        "target_database": target["database"],
        "changes": changes,
        "sql_statements": sql_statements,
        "rollback_sql_statements": rollback_sql_statements,
        "warnings": warnings,
        "requires_approval": bool(sql_statements),
    }


def validate_mysql_ddl(statements: list[str]) -> None:
    """仅允许白名单 CREATE/ALTER，默认拒绝 DROP 和 TRUNCATE 等破坏性语句。"""
    for statement in statements:
        if _FORBIDDEN_DDL.search(statement) or not _SAFE_DDL.match(statement):
            raise BadRequestException("MySQL 同步只允许受控 CREATE TABLE/ALTER TABLE，禁止 DROP/TRUNCATE 等操作")


def _execute_sync(config: dict[str, Any], credentials: dict[str, str], statements: list[str]) -> list[dict[str, Any]]:
    validate_mysql_ddl(statements)
    connection = _connect(config, credentials)
    results: list[dict[str, Any]] = []
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                affected = cursor.execute(statement)
                results.append({"sql": statement, "affected_rows": affected})
        return results
    finally:
        connection.close()


async def execute_mysql_ddl(
    config: dict[str, Any], credentials: dict[str, str], statements: list[str]
) -> list[dict[str, Any]]:
    """在线程中顺序执行已审批白名单 DDL，并返回逐条日志。"""
    try:
        await validate_tool_hostname(str(config["host"]), int(config.get("port", 3306)))
        return await asyncio.to_thread(_execute_sync, config, credentials, statements)
    except BadRequestException:
        raise
    except Exception as exc:
        raise ExternalServiceException(f"MySQL 同步执行失败：{type(exc).__name__}") from exc


def _rollback_sync(config: dict[str, Any], credentials: dict[str, str], statements: list[str]) -> list[dict[str, Any]]:
    """只执行系统根据执行前快照生成的有限逆向 ALTER 语句。"""
    for statement in statements:
        if not _SAFE_ROLLBACK_DDL.match(statement):
            raise BadRequestException("MySQL 回滚语句超出受控白名单")
    connection = _connect(config, credentials)
    results: list[dict[str, Any]] = []
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                affected = cursor.execute(statement)
                results.append({"sql": statement, "affected_rows": affected})
        return results
    finally:
        connection.close()


async def execute_mysql_rollback(
    config: dict[str, Any], credentials: dict[str, str], statements: list[str]
) -> list[dict[str, Any]]:
    """校验目标地址后在线程中执行已保存的逆向 SQL。"""
    try:
        await validate_tool_hostname(str(config["host"]), int(config.get("port", 3306)))
        return await asyncio.to_thread(_rollback_sync, config, credentials, statements)
    except BadRequestException:
        raise
    except Exception as exc:
        raise ExternalServiceException(f"MySQL 回滚执行失败：{type(exc).__name__}") from exc
