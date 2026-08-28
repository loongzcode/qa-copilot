def describe_exception(exc: BaseException) -> str:
    """生成适合写入后台日志的错误文本，避免无消息异常显示成空白。"""

    error_type = type(exc).__name__
    detail = str(exc).strip()
    return f"{error_type}: {detail}" if detail else error_type
