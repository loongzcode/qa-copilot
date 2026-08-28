import logging
import math
from functools import lru_cache

import tiktoken

logger = logging.getLogger(__name__)

# AI 回答成功后，如果服务商返回了 output_tokens，优先使用服务商的准确值；没有返回时再调用这个工具估算。
@lru_cache(maxsize=1)
def _get_encoding() -> tiktoken.Encoding | None:
    try:
        token = tiktoken.get_encoding("cl100k_base")
        if token is not None:
            return token
    except Exception:
        logger.warning(
            "无法加载 cl100k_base 编码，将使用保守 Token 估算",
            exc_info=True,
        )
        return None


def count_text_tokens(text: str) -> int:
    """
    优先使用 tiktoken 精确估算；
    编码资源不可用时使用 UTF-8 字节数进行保守降级；
    该结果用于上下文预算和记忆压缩阈值，不作为模型账单依据。
    """
    if not text:
        return 0
    encoding = _get_encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    #   获取 UTF-8 字节长度
    #     每 2 个字节保守估算为 1 Token
    #     使用 math.ceil 向上取整
    #     至少返回 1
    token = max(1, math.ceil(len(text.encode("utf-8")) / 2))
    return token
