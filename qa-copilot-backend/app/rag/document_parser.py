from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document as open_docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


@dataclass(slots=True)
class ParsedSection:
    """解析器输出的结构化正文段，保留页码和章节定位信息。"""

    content: str
    page_no: int | None = None
    section_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _clean_content(value: str) -> str:
    """统一换行并去掉行尾空白，避免无意义字符进入 Embedding。"""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _split_bounded_content(content: str, max_chars: int) -> Iterator[str]:
    """把单个超长文本块拆成有上限的小段。

    功能：优先在换行处截断；找不到合适换行时按字符上限硬切。
    作用：PDF 单页、DOCX 段落或 TXT 单行异常大时，保证后续切片器一次只接收
    有限文本，不因一段内容过大而产生内存尖峰。
    为什么用它：文件格式本身不限制单页或单行长度，仅对文件逐行读取仍无法
    提供严格上限；字符级兜底可以给所有解析格式统一的内存边界。
    """

    remaining = _clean_content(content)
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = max_chars
        part = remaining[:split_at].strip()
        if part:
            yield part
        remaining = remaining[split_at:].lstrip()
    if remaining:
        yield remaining


def _iter_pdf(path: Path, max_section_chars: int) -> Iterator[ParsedSection]:
    """逐页解析 PDF，并把异常大的单页继续分段。"""

    reader = PdfReader(path)
    for page_index, page in enumerate(reader.pages, start=1):
        for part_index, content in enumerate(
            _split_bounded_content(page.extract_text() or "", max_section_chars),
            start=1,
        ):
            yield ParsedSection(
                content=content,
                page_no=page_index,
                section_title=f"第 {page_index} 页",
                metadata={"source": "pdf", "section_part": part_index},
            )


def _iter_docx_blocks(path: Path) -> Iterator[Paragraph | Table]:
    """按 DOCX XML 中的真实顺序遍历段落和表格。"""

    document = open_docx(path)
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _iter_docx(path: Path, max_section_chars: int) -> Iterator[ParsedSection]:
    """按标题和字符上限逐段产出 DOCX 内容。"""

    current_title: str | None = None
    current_lines: list[str] = []
    current_chars = 0
    part_index = 0

    for block in _iter_docx_blocks(path):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style_name = block.style.name if block.style is not None else ""
            if style_name.lower().startswith("heading"):
                content = _clean_content("\n".join(current_lines))
                if content:
                    part_index += 1
                    yield ParsedSection(
                        content=content,
                        section_title=current_title,
                        metadata={"source": "docx", "section_part": part_index},
                    )
                current_title = text
                current_lines = []
                current_chars = 0
                part_index = 0
                continue
            block_text = text
        else:
            table_lines: list[str] = []
            for row in block.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if any(cells):
                    table_lines.append(" | ".join(cells))
            block_text = "\n".join(table_lines)

        for bounded_part in _split_bounded_content(block_text, max_section_chars):
            separator_chars = 1 if current_lines else 0
            if (
                current_lines
                and current_chars + separator_chars + len(bounded_part)
                > max_section_chars
            ):
                part_index += 1
                yield ParsedSection(
                    content=_clean_content("\n".join(current_lines)),
                    section_title=current_title,
                    metadata={"source": "docx", "section_part": part_index},
                )
                current_lines = []
                current_chars = 0
                separator_chars = 0
            current_lines.append(bounded_part)
            current_chars += separator_chars + len(bounded_part)

    content = _clean_content("\n".join(current_lines))
    if content:
        part_index += 1
        yield ParsedSection(
            content=content,
            section_title=current_title,
            metadata={"source": "docx", "section_part": part_index},
        )


def _iter_line_document(
    path: Path,
    *,
    source: str,
    max_section_chars: int,
    heading_pattern: re.Pattern[str] | None = None,
) -> Iterator[ParsedSection]:
    """逐行读取 Markdown/TXT，按标题或字符上限产出正文段。"""

    current_title: str | None = None
    current_lines: list[str] = []
    current_chars = 0
    part_index = 0

    with path.open("r", encoding="utf-8") as stream:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            heading = heading_pattern.match(line) if heading_pattern is not None else None
            if heading:
                content = _clean_content("\n".join(current_lines))
                if content:
                    part_index += 1
                    yield ParsedSection(
                        content=content,
                        section_title=current_title,
                        metadata={"source": source, "section_part": part_index},
                    )
                current_title = heading.group(1).strip()
                current_lines = []
                current_chars = 0
                part_index = 0
                continue

            # 空行本身没有正文，但它是段落边界。保留一个空字符串，使后续
            # RecursiveCharacterTextSplitter 仍能优先按双换行拆分。
            if not line:
                if current_lines and current_lines[-1] != "":
                    if current_chars + 1 > max_section_chars:
                        part_index += 1
                        yield ParsedSection(
                            content=_clean_content("\n".join(current_lines)),
                            section_title=current_title,
                            metadata={"source": source, "section_part": part_index},
                        )
                        current_lines = []
                        current_chars = 0
                    else:
                        current_lines.append("")
                        current_chars += 1
                continue

            for bounded_part in _split_bounded_content(line, max_section_chars):
                separator_chars = 1 if current_lines else 0
                if (
                    current_lines
                    and current_chars + separator_chars + len(bounded_part)
                    > max_section_chars
                ):
                    part_index += 1
                    yield ParsedSection(
                        content=_clean_content("\n".join(current_lines)),
                        section_title=current_title,
                        metadata={"source": source, "section_part": part_index},
                    )
                    current_lines = []
                    current_chars = 0
                    separator_chars = 0
                current_lines.append(bounded_part)
                current_chars += separator_chars + len(bounded_part)

    content = _clean_content("\n".join(current_lines))
    if content:
        part_index += 1
        yield ParsedSection(
            content=content,
            section_title=current_title,
            metadata={"source": source, "section_part": part_index},
        )


def iter_document_sections(
    path: Path,
    extension: str,
    *,
    max_section_chars: int = 64 * 1024,
) -> Iterator[ParsedSection]:
    """按需逐段解析知识文档，而不是一次返回全部正文。

    功能：根据扩展名选择 PDF、DOCX、Markdown 或 TXT 解析器，并返回惰性迭代器。
    作用：索引 Service 每次只消费下一段，解析结果无需整篇常驻 Worker 内存。
    为什么用它：生成器天然适合流水线；保留 ``parse_document`` 列表包装器，则让
    小文件调用方和旧测试仍可使用简单接口。
    """

    if max_section_chars <= 0:
        raise ValueError("单个解析段字符上限必须大于 0")

    normalized_extension = extension.lower()
    if normalized_extension == ".pdf":
        yield from _iter_pdf(path, max_section_chars)
    elif normalized_extension == ".docx":
        yield from _iter_docx(path, max_section_chars)
    elif normalized_extension == ".md":
        yield from _iter_line_document(
            path,
            source="markdown",
            max_section_chars=max_section_chars,
            heading_pattern=re.compile(r"^#{1,6}\s+(.+?)\s*$"),
        )
    elif normalized_extension == ".txt":
        yield from _iter_line_document(
            path,
            source="text",
            max_section_chars=max_section_chars,
        )
    else:
        raise ValueError(f"不支持解析的文档格式：{extension}")


def parse_document(path: Path, extension: str) -> list[ParsedSection]:
    """完整解析小文档；大文档索引应优先使用 ``iter_document_sections``。"""

    sections = list(iter_document_sections(path, extension))
    if not sections:
        raise ValueError("文档中没有提取到可索引的正文")
    return sections
