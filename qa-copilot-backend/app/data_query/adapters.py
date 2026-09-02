"""MySQL 与 PostgreSQL 数据查询适配器。"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import pymysql

from app.core.constants import DataSourceDatabaseType
from app.exceptions import BadRequestException, ExternalServiceException
from app.tools.network_guard import validate_tool_hostname

_NAMED_PARAMETER = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def json_safe(value: Any) -> Any:
    """把数据库驱动返回的特殊类型转换成可以写入 JSONB 和返回前端的值。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, UUID, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return f"<binary:{len(value)} bytes>"
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return str(value)


@dataclass(frozen=True, slots=True)
class DataSourceConnectionResult:
    database_version: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class QueryPlanResult:
    estimated_rows: int | None
    full_table_scan: bool
    raw_plan: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReadOnlyQueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool
    latency_ms: int


class DataSourceAdapter(Protocol):
    """不同数据库必须提供的统一受控查询能力。"""

    async def test_connection(self) -> DataSourceConnectionResult: ...

    async def introspect_metadata(self, max_tables: int) -> dict[str, Any]: ...

    async def explain(self, sql: str, parameters: dict[str, Any]) -> QueryPlanResult: ...

    async def execute(self, sql: str, parameters: dict[str, Any], max_rows: int) -> ReadOnlyQueryResult: ...


class MySQLDataSourceAdapter:
    """使用 PyMySQL 在线程中访问 MySQL，避免阻塞 FastAPI 事件循环。"""

    def __init__(self, config: dict[str, Any], credentials: dict[str, str], timeout_seconds: int) -> None:
        self.config = config
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds

    async def _validate_host(self) -> None:
        await validate_tool_hostname(str(self.config["host"]), int(self.config["port"]))

    def _connect(self):
        return pymysql.connect(
            host=str(self.config["host"]),
            port=int(self.config["port"]),
            user=self.credentials.get("username", ""),
            password=self.credentials.get("password", ""),
            database=str(self.config["database_name"]),
            charset=str(self.config.get("charset") or "utf8mb4"),
            connect_timeout=min(self.timeout_seconds, 30),
            read_timeout=self.timeout_seconds,
            write_timeout=self.timeout_seconds,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            ssl={} if self.config.get("ssl_enabled") else None,
            client_flag=0,
        )

    @staticmethod
    def _prepare_sql(sql: str) -> str:
        return _NAMED_PARAMETER.sub(lambda match: f"%({match.group(1)})s", sql)

    async def test_connection(self) -> DataSourceConnectionResult:
        await self._validate_host()

        def run() -> DataSourceConnectionResult:
            started_at = perf_counter()
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT VERSION() AS version")
                    row = cursor.fetchone() or {}
                return DataSourceConnectionResult(
                    database_version=str(row.get("version") or "MySQL"),
                    latency_ms=int((perf_counter() - started_at) * 1000),
                )
            finally:
                connection.close()

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            raise ExternalServiceException(f"MySQL 数据源连接失败：{type(exc).__name__}") from exc

    async def introspect_metadata(self, max_tables: int) -> dict[str, Any]:
        await self._validate_host()

        def run() -> dict[str, Any]:
            database = str(self.config["database_name"])
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME LIMIT %s",
                        (database, max_tables),
                    )
                    table_rows = cursor.fetchall()
                    table_names = [str(row["TABLE_NAME"]) for row in table_rows]
                    if not table_names:
                        return {"tables": []}
                    placeholders = ",".join(["%s"] * len(table_names))
                    cursor.execute(
                        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_COMMENT "
                        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s "
                        f"AND TABLE_NAME IN ({placeholders}) ORDER BY TABLE_NAME, ORDINAL_POSITION",
                        (database, *table_names),
                    )
                    column_rows = cursor.fetchall()
                    cursor.execute(
                        "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                        "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s "
                        f"AND TABLE_NAME IN ({placeholders}) AND REFERENCED_TABLE_NAME IS NOT NULL",
                        (database, *table_names),
                    )
                    foreign_key_rows = cursor.fetchall()
                tables = {
                    str(row["TABLE_NAME"]): {
                        "name": str(row["TABLE_NAME"]),
                        "comment": str(row.get("TABLE_COMMENT") or ""),
                        "columns": [],
                        "foreign_keys": [],
                    }
                    for row in table_rows
                }
                for row in column_rows:
                    tables[str(row["TABLE_NAME"])]["columns"].append(
                        {
                            "name": str(row["COLUMN_NAME"]),
                            "type": str(row["COLUMN_TYPE"]),
                            "nullable": row["IS_NULLABLE"] == "YES",
                            "primary_key": row["COLUMN_KEY"] == "PRI",
                            "comment": str(row.get("COLUMN_COMMENT") or ""),
                        }
                    )
                for row in foreign_key_rows:
                    tables[str(row["TABLE_NAME"])]["foreign_keys"].append(
                        {
                            "column": str(row["COLUMN_NAME"]),
                            "referenced_table": str(row["REFERENCED_TABLE_NAME"]),
                            "referenced_column": str(row["REFERENCED_COLUMN_NAME"]),
                        }
                    )
                return {"tables": list(tables.values())}
            finally:
                connection.close()

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            raise ExternalServiceException(f"MySQL 元数据读取失败：{type(exc).__name__}") from exc

    async def explain(self, sql: str, parameters: dict[str, Any]) -> QueryPlanResult:
        await self._validate_host()

        def run() -> QueryPlanResult:
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("EXPLAIN FORMAT=JSON " + self._prepare_sql(sql), parameters)
                    row = cursor.fetchone() or {}
                raw_value = next(iter(row.values()), "{}")
                raw_plan = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                query_block = raw_plan.get("query_block", {}) if isinstance(raw_plan, dict) else {}
                estimated_rows = _sum_mysql_plan_rows(query_block)
                return QueryPlanResult(
                    estimated_rows=estimated_rows,
                    full_table_scan=_mysql_has_full_scan(query_block),
                    raw_plan=json_safe(raw_plan),
                )
            finally:
                connection.close()

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            raise BadRequestException(f"MySQL 查询计划生成失败：{type(exc).__name__}") from exc

    async def execute(self, sql: str, parameters: dict[str, Any], max_rows: int) -> ReadOnlyQueryResult:
        await self._validate_host()

        def run() -> ReadOnlyQueryResult:
            started_at = perf_counter()
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET SESSION MAX_EXECUTION_TIME=%s", (self.timeout_seconds * 1000,))
                    cursor.execute("START TRANSACTION READ ONLY")
                    cursor.execute(self._prepare_sql(sql), parameters)
                    raw_rows = list(cursor.fetchmany(max_rows + 1))
                    columns = [str(item[0]) for item in (cursor.description or [])]
                connection.rollback()
                truncated = len(raw_rows) > max_rows
                rows = [{str(key): json_safe(value) for key, value in row.items()} for row in raw_rows[:max_rows]]
                return ReadOnlyQueryResult(columns, rows, truncated, int((perf_counter() - started_at) * 1000))
            finally:
                connection.close()

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            raise ExternalServiceException(f"MySQL 只读查询失败：{type(exc).__name__}") from exc


class PostgreSQLDataSourceAdapter:
    """使用 asyncpg 执行 PostgreSQL 只读事务。"""

    def __init__(self, config: dict[str, Any], credentials: dict[str, str], timeout_seconds: int) -> None:
        self.config = config
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds

    async def _validate_host(self) -> None:
        await validate_tool_hostname(str(self.config["host"]), int(self.config["port"]))

    async def _connect(self):
        return await asyncpg.connect(
            host=str(self.config["host"]),
            port=int(self.config["port"]),
            user=self.credentials.get("username", ""),
            password=self.credentials.get("password", ""),
            database=str(self.config["database_name"]),
            ssl=True if self.config.get("ssl_enabled") else None,
            timeout=min(self.timeout_seconds, 30),
            command_timeout=self.timeout_seconds,
        )

    @staticmethod
    def _prepare_sql(sql: str, parameters: dict[str, Any]) -> tuple[str, list[Any]]:
        ordered_names: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in parameters:
                raise BadRequestException(f"SQL 缺少绑定参数：{name}")
            if name not in ordered_names:
                ordered_names.append(name)
            return f"${ordered_names.index(name) + 1}"

        return _NAMED_PARAMETER.sub(replace, sql), [parameters[name] for name in ordered_names]

    async def test_connection(self) -> DataSourceConnectionResult:
        await self._validate_host()
        started_at = perf_counter()
        try:
            connection = await self._connect()
            try:
                version = await connection.fetchval("SELECT version()")
            finally:
                await connection.close()
            return DataSourceConnectionResult(str(version or "PostgreSQL"), int((perf_counter() - started_at) * 1000))
        except Exception as exc:
            raise ExternalServiceException(f"PostgreSQL 数据源连接失败：{type(exc).__name__}") from exc

    async def introspect_metadata(self, max_tables: int) -> dict[str, Any]:
        await self._validate_host()
        schema = str(self.config.get("schema_name") or "public")
        connection = await self._connect()
        try:
            table_rows = await connection.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=$1 AND table_type='BASE TABLE' ORDER BY table_name LIMIT $2",
                schema,
                max_tables,
            )
            table_names = [str(row["table_name"]) for row in table_rows]
            if not table_names:
                return {"tables": []}
            column_rows = await connection.fetch(
                "SELECT table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_schema=$1 AND table_name=ANY($2::text[]) "
                "ORDER BY table_name, ordinal_position",
                schema,
                table_names,
            )
            primary_rows = await connection.fetch(
                "SELECT kcu.table_name, kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "AND tc.table_schema=kcu.table_schema WHERE tc.table_schema=$1 "
                "AND tc.constraint_type='PRIMARY KEY' AND kcu.table_name=ANY($2::text[])",
                schema,
                table_names,
            )
            foreign_rows = await connection.fetch(
                "SELECT kcu.table_name, kcu.column_name, ccu.table_name AS referenced_table, "
                "ccu.column_name AS referenced_column FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "AND tc.table_schema=kcu.table_schema JOIN information_schema.constraint_column_usage ccu "
                "ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema "
                "WHERE tc.table_schema=$1 AND tc.constraint_type='FOREIGN KEY' "
                "AND kcu.table_name=ANY($2::text[])",
                schema,
                table_names,
            )
        finally:
            await connection.close()
        primary_keys = {(str(row["table_name"]), str(row["column_name"])) for row in primary_rows}
        tables = {
            name: {"name": name, "comment": "", "columns": [], "foreign_keys": []} for name in table_names
        }
        for row in column_rows:
            table_name = str(row["table_name"])
            column_name = str(row["column_name"])
            tables[table_name]["columns"].append(
                {
                    "name": column_name,
                    "type": str(row["data_type"]),
                    "nullable": row["is_nullable"] == "YES",
                    "primary_key": (table_name, column_name) in primary_keys,
                    "comment": "",
                }
            )
        for row in foreign_rows:
            tables[str(row["table_name"])]["foreign_keys"].append(
                {
                    "column": str(row["column_name"]),
                    "referenced_table": str(row["referenced_table"]),
                    "referenced_column": str(row["referenced_column"]),
                }
            )
        return {"tables": list(tables.values())}

    async def explain(self, sql: str, parameters: dict[str, Any]) -> QueryPlanResult:
        await self._validate_host()
        prepared_sql, values = self._prepare_sql(sql, parameters)
        connection = await self._connect()
        transaction = connection.transaction(readonly=True)
        try:
            await transaction.start()
            await connection.execute(f"SET LOCAL statement_timeout = {self.timeout_seconds * 1000}")
            raw = await connection.fetchval("EXPLAIN (FORMAT JSON) " + prepared_sql, *values)
            raw_plan = json.loads(raw) if isinstance(raw, str) else raw
            root = raw_plan[0].get("Plan", {}) if isinstance(raw_plan, list) and raw_plan else {}
            return QueryPlanResult(
                estimated_rows=int(root.get("Plan Rows", 0) or 0),
                full_table_scan=_postgres_has_seq_scan(root),
                raw_plan=json_safe({"plan": raw_plan}),
            )
        except Exception as exc:
            raise BadRequestException(f"PostgreSQL 查询计划生成失败：{type(exc).__name__}") from exc
        finally:
            await transaction.rollback()
            await connection.close()

    async def execute(self, sql: str, parameters: dict[str, Any], max_rows: int) -> ReadOnlyQueryResult:
        await self._validate_host()
        prepared_sql, values = self._prepare_sql(sql, parameters)
        connection = await self._connect()
        transaction = connection.transaction(readonly=True)
        started_at = perf_counter()
        try:
            await transaction.start()
            await connection.execute(f"SET LOCAL statement_timeout = {self.timeout_seconds * 1000}")
            records = list(await connection.fetch(prepared_sql, *values))
            truncated = len(records) > max_rows
            records = records[:max_rows]
            columns = list(records[0].keys()) if records else []
            rows = [{str(key): json_safe(value) for key, value in dict(record).items()} for record in records]
            return ReadOnlyQueryResult(columns, rows, truncated, int((perf_counter() - started_at) * 1000))
        except Exception as exc:
            raise ExternalServiceException(f"PostgreSQL 只读查询失败：{type(exc).__name__}") from exc
        finally:
            await transaction.rollback()
            await connection.close()


def _sum_mysql_plan_rows(value: Any) -> int:
    if isinstance(value, dict):
        total = int(value.get("rows_examined_per_scan", 0) or 0)
        return total + sum(_sum_mysql_plan_rows(item) for item in value.values())
    if isinstance(value, list):
        return sum(_sum_mysql_plan_rows(item) for item in value)
    return 0


def _mysql_has_full_scan(value: Any) -> bool:
    if isinstance(value, dict):
        if str(value.get("access_type", "")).upper() == "ALL":
            return True
        return any(_mysql_has_full_scan(item) for item in value.values())
    if isinstance(value, list):
        return any(_mysql_has_full_scan(item) for item in value)
    return False


def _postgres_has_seq_scan(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("Node Type") == "Seq Scan":
            return True
        return any(_postgres_has_seq_scan(item) for item in value.values())
    if isinstance(value, list):
        return any(_postgres_has_seq_scan(item) for item in value)
    return False


def create_data_source_adapter(
    database_type: DataSourceDatabaseType,
    config: dict[str, Any],
    credentials: dict[str, str],
    timeout_seconds: int,
) -> DataSourceAdapter:
    """根据数据源类型创建对应适配器，调用方不再编写数据库类型分支。"""

    if database_type is DataSourceDatabaseType.MYSQL:
        return MySQLDataSourceAdapter(config, credentials, timeout_seconds)
    if database_type is DataSourceDatabaseType.POSTGRESQL:
        return PostgreSQLDataSourceAdapter(config, credentials, timeout_seconds)
    raise BadRequestException("暂不支持该数据库类型")
