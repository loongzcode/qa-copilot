from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.document_parser import ParsedSection


@dataclass(slots=True)
class DocumentChunk:
    """准备写入数据库并生成向量的单个知识切片。"""

    chunk_index: int
    content: str
    token_count: int
    page_no: int | None
    section_title: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def iter_document_chunks(
    sections: Iterable[ParsedSection],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> Iterator[DocumentChunk]:
    """逐个生成知识切片，不把整篇文档的切片同时放进内存。

    功能：保留解析器提供的章节边界，并在超长章节内部按 Token 递归切片。
    作用：连接流式解析器与 Embedding 批处理；调用方可以只取固定数量的切片。
    为什么用它：生成器只保留当前章节的拆分结果。返回完整列表虽然调用简单，
    但大文档会同时保存全部正文副本，增加 Worker 内存占用。
    """

    if chunk_overlap >= chunk_size:
        raise ValueError("切片重叠 Token 数必须小于单个切片大小")

    encoding = tiktoken.get_encoding("cl100k_base")
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", ". ", " ", ""],
    )

    chunk_index = 0
    for section_index, section in enumerate(sections):
        for content in splitter.split_text(section.content):
            normalized = content.strip()
            if not normalized:
                continue
            yield DocumentChunk(
                chunk_index=chunk_index,
                content=normalized,
                token_count=len(encoding.encode(normalized)),
                page_no=section.page_no,
                section_title=section.section_title,
                metadata={**section.metadata, "section_index": section_index},
            )
            chunk_index += 1


def take_chunk_batch(
    chunks: Iterator[DocumentChunk],
    batch_size: int,
) -> list[DocumentChunk]:
    """从惰性切片流中最多取得一个固定大小的批次。

    功能：连续调用 ``next``，遇到批次上限或迭代结束时返回当前批次。
    作用：索引 Service 在线程中调用它，避免同步文件解析阻塞异步事件循环。
    为什么用它：不能让 ``StopIteration`` 直接穿过 ``asyncio.to_thread`` 的
    Future；在同步辅助函数内消费并返回普通列表更安全，也明确限制批次内存。
    """

    if batch_size <= 0:
        raise ValueError("切片批次大小必须大于 0")

    batch: list[DocumentChunk] = []
    for _ in range(batch_size):
        try:
            batch.append(next(chunks))
        except StopIteration:
            break
    return batch


def split_document_sections(
    sections: Iterable[ParsedSection],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[DocumentChunk]:
    """完整切分小文档；大文档索引应优先使用 ``iter_document_chunks``。"""

    chunks = list(
        iter_document_chunks(
            sections,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    )

    if not chunks:
        raise ValueError("文档切片结果为空")
    return chunks
