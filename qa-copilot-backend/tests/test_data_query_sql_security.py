"""智能数据查询 SQL 安全边界的单元测试。"""

import pytest
from app.core.constants import DataSourceDatabaseType
from app.data_query.adapters import MySQLDataSourceAdapter, PostgreSQLDataSourceAdapter
from app.data_query.sql_security import SQLSafetyValidator


@pytest.fixture
def validator() -> SQLSafetyValidator:
    return SQLSafetyValidator()


def test_mysql_select_is_parameterized_and_limited(validator: SQLSafetyValidator) -> None:
    result = validator.validate(
        sql="SELECT id, username FROM users WHERE created_at >= :start_time ORDER BY id DESC",
        database_type=DataSourceDatabaseType.MYSQL,
        parameters={"start_time": "2026-08-01"},
        allowed_tables={"users"},
        sensitive_columns={"users": {"password_hash"}},
        max_rows=200,
    )

    assert result.valid is True
    assert result.referenced_tables == ["users"]
    assert "LIMIT 201" in result.normalized_sql


def test_postgresql_cte_is_allowed(validator: SQLSafetyValidator) -> None:
    result = validator.validate(
        sql=(
            "WITH daily AS (SELECT created_at::date AS day, COUNT(id) AS amount FROM users "
            "GROUP BY created_at::date) SELECT day, amount FROM daily ORDER BY day"
        ),
        database_type=DataSourceDatabaseType.POSTGRESQL,
        parameters={},
        allowed_tables={"users"},
        sensitive_columns={},
        max_rows=100,
    )

    assert result.valid is True
    assert result.referenced_tables == ["users"]


@pytest.mark.parametrize(
    ("sql", "expected_error"),
    [
        ("DELETE FROM users WHERE id = 1", "只允许 SELECT"),
        ("SELECT id FROM users; SELECT id FROM orders", "一次只能执行一条 SQL"),
        ("SELECT * FROM users", "禁止 SELECT *"),
        ("SELECT id FROM audit_logs", "表不在数据源查询白名单"),
        ("SELECT password_hash FROM users", "敏感字段"),
        ("SELECT u.password_hash FROM users AS u", "users.password_hash"),
        ("SELECT id FROM users WHERE id = :user_id", "缺少 SQL 绑定参数"),
        ("SELECT id, pg_sleep(10) FROM users", "禁止调用高风险数据库函数"),
    ],
)
def test_unsafe_sql_is_rejected(validator: SQLSafetyValidator, sql: str, expected_error: str) -> None:
    result = validator.validate(
        sql=sql,
        database_type=DataSourceDatabaseType.MYSQL,
        parameters={},
        allowed_tables={"users"},
        sensitive_columns={"users": {"password_hash"}},
        max_rows=200,
    )

    assert result.valid is False
    assert any(expected_error in error for error in result.errors)


def test_database_adapters_convert_named_parameters() -> None:
    mysql_sql = MySQLDataSourceAdapter._prepare_sql("SELECT id FROM users WHERE id=:user_id")
    postgres_sql, values = PostgreSQLDataSourceAdapter._prepare_sql(
        "SELECT id FROM users WHERE id=:user_id OR manager_id=:user_id",
        {"user_id": 7},
    )

    assert mysql_sql == "SELECT id FROM users WHERE id=%(user_id)s"
    assert postgres_sql == "SELECT id FROM users WHERE id=$1 OR manager_id=$1"
    assert values == [7]
