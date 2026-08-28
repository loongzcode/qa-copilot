from pathlib import Path
from zipfile import BadZipFile, ZipFile, is_zipfile

ALLOWED_DOCUMENT_MIME_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".md": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
}

ALLOWED_DOCUMENT_EXTENSIONS = frozenset(ALLOWED_DOCUMENT_MIME_TYPES)
MAX_DOCX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def validate_document_content(path: Path, extension: str) -> None:
    """根据真实文件内容校验格式；失败时抛出 ValueError。"""

    if extension == ".pdf":
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError("PDF 文件头不正确")
        return

    if extension == ".docx":
        if not is_zipfile(path):
            raise ValueError("DOCX 不是有效的 ZIP 文档")

        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                required_names = {"[Content_Types].xml", "word/document.xml"}
                if not required_names.issubset(names):
                    raise ValueError("DOCX 缺少必要的文档结构")

                uncompressed_size = sum(item.file_size for item in archive.infolist())
                if uncompressed_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise ValueError("DOCX 解压后的内容过大")

                if archive.testzip() is not None:
                    raise ValueError("DOCX 压缩包内容损坏")
        except BadZipFile as exc:
            raise ValueError("DOCX 文件已损坏") from exc
        return

    if extension in {".md", ".txt"}:
        content = path.read_bytes()
        if b"\x00" in content:
            raise ValueError("文本文件包含二进制内容")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("文本文件必须使用 UTF-8 编码") from exc
        return

    raise ValueError("不支持的知识文档格式")
