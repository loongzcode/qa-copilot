"""文件、MySQL 和 Nacos 工具的确定性安全测试。"""

from types import SimpleNamespace

import pytest
from app.exceptions import BadRequestException
from app.tools.file_tools import generate_file, parse_file, validate_records
from app.tools.mysql_tools import build_create_table_sql, compare_mysql_snapshots, validate_mysql_ddl
from app.tools.nacos_tools import compare_nacos_content


def _csv_template():
    return SimpleNamespace(
        name="清算明细",
        file_format="CSV",
        encoding="UTF-8",
        delimiter=",",
        fields=[
            {
                "name": "流水号",
                "sourceField": "serialNo",
                "dataType": "STRING",
                "required": True,
                "length": 20,
                "mapping": {},
            },
            {
                "name": "金额",
                "sourceField": "amount",
                "dataType": "DECIMAL",
                "required": True,
                "precision": 2,
                "mapping": {},
            },
        ],
        trailer_config={"totalAmountField": "金额"},
    )


def test_file_generate_and_parse_csv() -> None:
    """CSV 生成结果可以按同一模板读回，金额按两位精度规范化。"""
    template = _csv_template()
    content, extension, _, report = generate_file(
        template,
        [{"serialNo": "A001", "amount": "12.3"}],
    )

    assert extension == "csv"
    assert report["record_count"] == 1
    assert report["total_amount"] == "12.30"
    parsed = parse_file(template, content)
    assert parsed[0]["流水号"] == "A001"


def test_file_validation_reports_row_and_field() -> None:
    """错误报告必须定位到具体行和字段，不能只返回笼统失败。"""
    _, errors = validate_records(
        [{"serialNo": "", "amount": "not-number"}],
        _csv_template().fields,
    )
    assert {(item["row"], item["field"]) for item in errors} == {
        (1, "流水号"),
        (1, "金额"),
    }


def test_mysql_compare_generates_add_column_and_warning() -> None:
    """缺少字段生成 ADD，字段变化生成 MODIFY 并突出风险。"""
    source = {
        "database": "source",
        "tables": {
            "orders": {
                "columns": {
                    "id": {"type": "bigint", "nullable": False},
                    "remark": {"type": "varchar(200)", "nullable": True},
                }
            }
        },
    }
    target = {
        "database": "target",
        "tables": {
            "orders": {
                "columns": {
                    "id": {"type": "int", "nullable": False},
                }
            }
        },
    }
    result = compare_mysql_snapshots(source, target)
    assert any("ADD COLUMN `remark`" in sql for sql in result["sql_statements"])
    assert any("MODIFY COLUMN `id`" in sql for sql in result["sql_statements"])
    assert any("DROP COLUMN `remark`" in sql for sql in result["rollback_sql_statements"])
    assert any("MODIFY COLUMN `id`" in sql for sql in result["rollback_sql_statements"])
    assert result["warnings"]


def test_mysql_rejects_destructive_ddl() -> None:
    """即使任务已审批，默认执行器仍拒绝 DROP/TRUNCATE。"""
    with pytest.raises(BadRequestException):
        validate_mysql_ddl(["DROP TABLE users;"])


def test_mysql_build_create_table_contains_primary_key_and_foreign_key() -> None:
    """目标缺表时，建表建议必须保留主键、普通索引、外键和引用动作。"""
    sql = build_create_table_sql(
        "orders",
        {
            "engine": "InnoDB",
            "comment": "订单",
            "columns": {
                "id": {"position": 1, "type": "bigint", "nullable": False, "extra": "auto_increment"},
                "user_id": {"position": 2, "type": "bigint", "nullable": False},
            },
            "indexes": {
                "PRIMARY": {"unique": True, "type": "BTREE", "columns": ["id"]},
                "ix_orders_user": {"unique": False, "type": "BTREE", "columns": ["user_id"]},
            },
            "constraints": {
                "fk_orders_user": {
                    "name": "fk_orders_user",
                    "type": "FOREIGN KEY",
                    "columns": ["user_id"],
                    "referenced_table": "users",
                    "referenced_columns": ["id"],
                    "update_rule": "RESTRICT",
                    "delete_rule": "CASCADE",
                }
            },
        },
    )
    assert "PRIMARY KEY (`id`)" in sql
    assert "KEY `ix_orders_user` (`user_id`)" in sql
    assert "REFERENCES `users` (`id`)" in sql
    assert "ON DELETE CASCADE" in sql


def test_nacos_compare_redacts_sensitive_values() -> None:
    """配置差异可以显示字段路径，但密码和 Token 正文始终脱敏。"""
    result = compare_nacos_content(
        "database:\n  password: old-secret\nfeature: true\n",
        "database:\n  password: new-secret\nfeature: false\n",
        "yaml",
    )
    rendered = str(result)
    assert "old-secret" not in rendered
    assert "new-secret" not in rendered
    assert any(item["path"] == "feature" for item in result["changes"])
