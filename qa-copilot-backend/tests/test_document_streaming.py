"""流式文档解析与切片的确定性单元测试。"""

from pathlib import Path

from app.rag import (
    ParsedSection,
    iter_document_chunks,
    iter_document_sections,
    take_chunk_batch,
)
from app.rag.document_parser import _split_bounded_content


def test_text_parser_and_chunker_are_bounded() -> None:
    """超长文本块不能突破解析段上限，并可按指定批次消费切片。"""

    bounded_parts = list(_split_bounded_content("测试文本" * 2000, 128))
    assert bounded_parts
    assert all(len(part) <= 128 for part in bounded_parts)

    sections = (
        ParsedSection(content=part, metadata={"source": "unit-test"})
        for part in bounded_parts
    )
    chunks = iter_document_chunks(
        sections,
        chunk_size=100,
        chunk_overlap=10,
    )

    first_batch = take_chunk_batch(chunks, 3)
    second_batch = take_chunk_batch(chunks, 3)

    assert len(first_batch) == 3
    assert len(second_batch) == 3
    assert [chunk.chunk_index for chunk in first_batch + second_batch] == list(
        range(6)
    )
    assert all(chunk.content for chunk in first_batch + second_batch)


def test_markdown_parser_reads_existing_file_lazily() -> None:
    """真实 Markdown 文件应逐段读取且每段不超过配置的字符上限。"""

    sections = list(
        iter_document_sections(
            Path("README.md"),
            ".md",
            max_section_chars=1024,
        )
    )
    assert sections
    assert all(0 < len(section.content) <= 1024 for section in sections)
