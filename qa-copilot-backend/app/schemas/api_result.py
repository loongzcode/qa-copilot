from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResult[T](BaseModel):
    """与 Soybean Admin 请求适配器一致的统一响应结构。"""

    # 错误码不是用于计算的数字，而是前后端约定的标识。
    # 使用字符串才能保留成功码 "0000" 前面的三个 0。
    code: str = "0000"
    msg: str = "操作成功"
    data: T | None = None


def success(data: Any = None, message: str = "操作成功") -> ApiResult[Any]:
    return ApiResult(code="0000", msg=message, data=data)


def failure(message: str, code: str, data: Any = None) -> ApiResult[Any]:
    return ApiResult(code=code, msg=message, data=data)


class PageResult[T](BaseModel):
    """与脚手架表格分页字段保持一致。"""

    current: int
    size: int
    total: int
    records: list[T]
