from typing import Any


class BusinessException(Exception):
    """项目中所有可预期业务异常的父类。

    Service 只需要说明“发生了什么业务错误”，不需要依赖 FastAPI。
    全局异常处理器会把这里保存的信息转换成统一的 HTTP JSON 响应。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "4000",
        status_code: int = 400,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.data = data
        self.headers = headers
