import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.constants import (
    KnowledgeDocumentParseStatus,
    KnowledgeDocumentSourceType,
    KnowledgeDocumentType,
    OutboxAggregateType,
    OutboxEventType,
)
from app.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models import KnowledgeDocument, User
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.outbox_event_repository import OutboxEventRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.schemas.dto.knowledge_documents import KnowledgeDocumentUploadDTO
from app.schemas.vo.knowledge_documents import KnowledgeDocumentVO
from app.storage import DocumentStorage
from app.utils.knowledge_document_file import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    ALLOWED_DOCUMENT_MIME_TYPES,
    validate_document_content,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentPreview:
    content: AsyncIterator[bytes]
    mime_type: str
    filename: str


class KnowledgeDocumentService:
    def __init__(
            self,
            repository: KnowledgeDocumentRepository,
            outbox_event_repository: OutboxEventRepository,
            knowledge_base_repository: KnowledgeBaseRepository,
            test_modules_repository: TestModulesRepository,
            document_storage: DocumentStorage,
    ) -> None:
        self.repository = repository
        self.outbox_event_repository = outbox_event_repository
        self.knowledge_base_repository = knowledge_base_repository
        self.test_modules_repository = test_modules_repository
        self.document_storage = document_storage

    @staticmethod
    def _knowledge_document_read(
            document: KnowledgeDocument,
    ) -> KnowledgeDocumentVO:
        """把文档实体及查询附带的关系、统计字段转换成前端 VO。"""

        return KnowledgeDocumentVO(
            id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            module_id=document.module_id,
            module_name=document.module.name if document.module else None,
            document_type=document.document_type,
            title=document.title,
            source_type=document.source_type,
            source_url=document.source_url,
            original_filename=document.original_filename,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            version=document.version,
            parse_status=document.parse_status,
            error_message=document.error_message,
            index_task_id=document.index_task_id,
            index_queued_at=document.index_queued_at,
            index_started_at=document.index_started_at,
            index_heartbeat_at=document.index_heartbeat_at,
            index_completed_at=document.index_completed_at,
            index_recovery_count=document.index_recovery_count,
            metadata=document.document_metadata,
            chunk_count=document.chunk_count or 0,
            created_by=document.created_by,
            created_by_name=(
                document.creator.display_name
                if document.creator
                else None
            ),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    async def list_knowledge_documents(self,
                                       project_id: int,
                                       knowledge_base_id: int,
                                       current_user: User,
                                       document_type: KnowledgeDocumentType | None,
                                       parse_status: KnowledgeDocumentParseStatus | None,
                                       module_id: int | None,
                                       current: int,
                                       size: int,
                                       keyword: str
                                       ) -> tuple[list[KnowledgeDocumentVO], int]:
        # 1. 使用 project_id、knowledge_base_id 和 current_user 查询当前用户
        #    可访问的知识库。必须调用 get_accessible_knowledge_base()，不能只按
        #    knowledge_base_id 查询，否则会绕过 PROJECT/MANAGERS/PRIVATE 数据权限。
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user)
        # 2. 如果没有查到知识库，统一抛出：
        #    NotFoundException("知识库不存在或无权访问")。
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权访问")
        # 3. 调用文档 Repository 的 list_knowledge_documents() 查询文档分页数据。
        #    Repository 接收数据库中实际保存的字符串，因此两个枚举参数需要处理：
        #    - 参数不是 None 时传 `.value`；
        #    - 参数是 None 时仍然传 None，表示不按该字段过滤。
        #    同时传入 knowledge_base_id、module_id、current、size 和 keyword。
        documents, total = await self.repository.list_knowledge_documents(
            knowledge_base_id=knowledge_base_id,
            document_type=(
                document_type.value
                if document_type is not None
                else None
            ),
            parse_status=(
                parse_status.value if parse_status is not None else None
            ),
            module_id=module_id,
            current=current,
            size=size,
            keyword=keyword,

        )
        # 4. Repository 返回 documents 和 total。使用列表推导式调用
        #    self._knowledge_document_read(document)，把每个实体转换成 VO。
        records = [self._knowledge_document_read(document) for document in documents]
        # 5. 返回 `(records, total)`，API 会用它们构造 PageResult。
        return records, total

    async def upload_knowledge_document(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
            payload: KnowledgeDocumentUploadDTO,
            file: UploadFile,
    ) -> KnowledgeDocumentVO:
        """上传原始文件并创建 PENDING 文档记录，不在本方法中提交索引任务。

        功能：校验文件和数据权限，把原文件保存到 DocumentStorage，并在数据库
        创建等待处理的 KnowledgeDocument 记录。
        作用：完成知识文档生命周期的“接收原件”阶段；普通上传接口返回后，
        需要继续调用 submit_index() 才会把解析与索引任务交给 Celery。
        为什么用它：上传请求只负责可靠保存文件和业务档案，避免文件解析、切片、
        向量生成等耗时操作长时间占用 HTTP 请求，同时让失败重试边界更清晰。
        """

        # 第一阶段：校验业务访问范围。
        # 1. 使用 project_id、knowledge_base_id、current_user 调用
        #    knowledge_base_repository.get_accessible_knowledge_base()。
        #    查询不到时抛出“知识库不存在或无权访问”。
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权访问")
        # 2. 判断知识库是否启用。停用知识库可以保留和查看历史数据，
        #    但不能继续上传新文档，应抛出明确的 BadRequestException。
        if not knowledge_base.enabled:
            raise BadRequestException("已停用知识库不能继续上传新文档")
        # 3. payload.module_id 不为 None 时，必须调用 TestModulesRepository.get_module()
        #    校验模块真实存在并且属于 project_id。
        #    不能只相信前端传来的 module_id，否则可能把文档关联到其他项目的模块。
        if payload.module_id is not None:
            test_module = await self.test_modules_repository.get_module(
                project_id,
                payload.module_id,
            )
            if test_module is None:
                raise NotFoundException("项目模块不存在")
        # 第二阶段：校验并读取上传文件。
        # 4. 校验 file.filename：文件名不能为空，并取得安全的原始文件名。
        #    允许的扩展名为 .pdf、.docx、.md、.txt；不能只根据 Content-Type 判断，
        #    因为 Content-Type 是客户端传来的，不能完全信任。
        if not file.filename:
            raise BadRequestException("上传文件名不能为空")
        # 防止客户端传入 C:\fakepath\test.pdf 或 ../../test.pdf
        original_filename = file.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not original_filename:
            raise BadRequestException("上传文件名不能为空")
        if len(original_filename) > 300:
            raise BadRequestException("上传文件名不能超过 300 个字符")
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
            raise BadRequestException("只支持 PDF、DOCX、Markdown 和 TXT 文件")

        content_type = (file.content_type or "").lower()

        if content_type not in ALLOWED_DOCUMENT_MIME_TYPES[extension]:
            raise BadRequestException("文件类型与扩展名不匹配")

        # 5. 以固定大小的块循环读取 UploadFile，而不是不受限制地一次 read()：
        #    - 一边累计 size_bytes；
        #    - 一边调用 SHA-256 对象的 update()；
        #    - 一边把内容写入临时文件；
        #    - 一旦超过配置的最大文件大小立即停止并删除临时文件。
        #    读取结束后还要拒绝 0 字节空文件。
        chunk_size = 1024 * 1024
        max_size = settings.knowledge_document_max_size_bytes
        size_bytes = 0
        sha256_calculator = hashlib.sha256()
        temp_path: Path | None = None
        try:
            # with 管理的是我们准备写入的临时文件，
            # 不是 FastAPI 已经打开的 UploadFile。
            with NamedTemporaryFile(
                    mode="wb",
                    delete=False,
                    suffix=extension,
            ) as temp_steam:
                temp_path = Path(temp_steam.name)

                while True:
                    # 每次从上传文件中读取最多 1MB。
                    chunk = await file.read(chunk_size)
                    # read() 返回 b""，说明文件已经读完。
                    if not chunk:
                        break
                    size_bytes += len(chunk)

                    # 在写入磁盘前检查大小，避免超限内容继续落盘
                    if size_bytes > max_size:
                        max_size_mb = max_size // (1024 * 1024)
                        raise BadRequestException(
                            f"上传文件不能超过 {max_size_mb}MB"
                        )

                    # 把当前这块内容加入 SHA-256 计算
                    sha256_calculator.update(chunk)
                    # 把当前这块内容写入临时文件
                    await asyncio.to_thread(temp_steam.write, chunk)
            if size_bytes == 0:
                raise BadRequestException("不能上传空文件")
            # 读取结束后取得最终的 64 位 十六进制哈希
            sha256 = sha256_calculator.hexdigest()
        except Exception:
            # 校验或写入失败时，删除已经产生的临时文件。
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
        finally:
            # UploadFile 由我们使用完毕后主动关闭。
            await file.close()

        if temp_path is None:
            raise RuntimeError("上传文件没有生成临时文件")

        # 扩展名和 MIME 都可能伪造，因此在文件完整落盘后检查真实内容。
        try:
            await asyncio.to_thread(
                validate_document_content,
                temp_path,
                extension,
            )
        except ValueError as exc:
            temp_path.unlink(missing_ok=True)
            raise BadRequestException(str(exc)) from exc

        # 6. 调用 repository.get_by_sha256(knowledge_base_id, sha256) 检查重复内容。
        #    如果已经存在相同哈希的未删除文档，删除临时文件并抛出 ConflictException。
        try:
            duplicate_document = await self.repository.get_by_sha256(
                knowledge_base_id,
                sha256,
            )
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        if duplicate_document is not None:
            temp_path.unlink(missing_ok=True)
            raise ConflictException("请勿重复上传相同内容的文档")
        # 第三阶段：保证对象存储与数据库记录尽量一致。
        # 7. 生成不可猜测且不会重名的 object_key。建议结构：
        #    knowledge/{knowledge_base_id}/{当前年月}/{uuid}{扩展名}。
        #    object_key 只保存相对键，不保存本机绝对路径。
        current_month = datetime.now(UTC).strftime("%Y/%m")
        object_key = (
            f"knowledge/{knowledge_base_id}/{current_month}/"
            f"{uuid4().hex}{extension}"
        )

        # 8. 调用对象存储服务把临时文件保存到 object_key。
        #    开发环境可以使用本地实现，生产环境可以替换为 MinIO/S3 实现；
        #    Service 不应该自己拼接磁盘根目录或直接依赖某一种存储产品。
        try:
            await self.document_storage.save_file(temp_path, object_key)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        # 9. 创建 KnowledgeDocument 实体，至少填写：
        #    knowledge_base_id、module_id、document_type、title、source_type=UPLOAD、
        #    object_key、original_filename、mime_type、size_bytes、sha256、version=1、
        #    parse_status=PENDING、document_metadata、created_by。
        #    title 已由 DTO 去掉首尾空格；document_type 需要保存枚举的 value。
        document_title = payload.title or Path(original_filename).stem
        document = KnowledgeDocument(
            knowledge_base_id=knowledge_base_id,
            module_id=payload.module_id,
            document_type=payload.document_type.value,
            title=document_title,
            source_type=KnowledgeDocumentSourceType.UPLOAD.value,
            source_url=None,
            object_key=object_key,
            original_filename=original_filename,
            mime_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            version=1,
            parse_status=KnowledgeDocumentParseStatus.PENDING.value,
            error_message=None,
            document_metadata=payload.metadata,
            created_by=current_user.id,
        )

        # 10. repository.add(document) 后，在 try 中 commit()：
        #     - 提交失败时先 rollback()；
        #     - 再调用对象存储服务删除第 8 步保存的文件，避免产生孤儿文件；
        #     - 最后继续抛出原异常，交给统一异常处理器记录。
        self.repository.add(document)
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            try:
                await self.document_storage.delete_file(object_key)
            except Exception:
                logger.exception(
                    "数据库提交失败后清理知识文档对象失败",
                    extra={"object_key": object_key},
                )
            raise

        # 第四阶段：提交异步索引并返回结果。
        # 11. 文档先以 PENDING 状态入库。解析、切片、Embedding 和索引属于下一阶段
        #     的后台任务模块；在可靠任务队列或事务 Outbox 完成前，这里不能假装任务
        #     已经成功提交。后续索引接口将以该 PENDING 文档作为任务输入。

        # 12. 再调用 repository.get_document() 查询刚创建的文档：
        #     这样能统一取得 module、creator 和 chunk_count，而不必手动伪造 VO 字段。
        created_document = await self.repository.get_document(
            knowledge_base_id,
            document.id,
        )
        if created_document is None:
            raise RuntimeError("文档创建成功后无法重新查询")

        # 13. 使用 self._knowledge_document_read(document) 转换并返回 KnowledgeDocumentVO。
        return self._knowledge_document_read(created_document)

    async def submit_index(
            self,
            project_id: int,
            knowledge_base_id: int,
            document_id: int,
            current_user: User,
    ) -> KnowledgeDocumentVO:
        """在一个数据库事务中登记文档索引请求和发件箱事件。

        功能：校验用户与文档状态，把文档推进到 ``PENDING``，并创建一条等待
        发布的知识文档索引事件。

        作用：这是首次索引、重新索引和失败重试的统一入口。接口成功只代表
        PostgreSQL 已可靠记录任务；后续由发件箱发布器发送到 Redis。

        为什么用它：文档状态和发件箱事件共用同一个 ``AsyncSession``，只在
        最后执行一次 ``commit``，从而保证两项修改同时成功或同时回滚。
        """

        # 1. 先校验知识库访问权限，不能因为用户知道 document_id 就绕过
        #    PROJECT/MANAGERS/PRIVATE 可见范围。
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user,
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权访问")
        if not knowledge_base.enabled:
            raise BadRequestException("已停用知识库不能提交索引任务")

        # 2. 文档必须属于当前知识库且未删除。
        document = await self.repository.get_document(knowledge_base_id, document_id)
        if document is None:
            raise NotFoundException("知识文档不存在")
        if document.parse_status in {
            KnowledgeDocumentParseStatus.PARSING.value,
            KnowledgeDocumentParseStatus.INDEXING.value,
        }:
            raise ConflictException("文档正在处理中，请勿重复提交")
        if not document.object_key:
            raise BadRequestException("当前文档没有可供索引的原始文件")

        # 3. 直接修改当前 Session 已跟踪的文档实体，但暂时不提交。旧切片继续
        #    保留，只有 Worker 成功生成全部新向量后才会原子替换。
        document.parse_status = KnowledgeDocumentParseStatus.PENDING.value
        document.error_message = None
        document.index_task_id = None
        document.index_queued_at = datetime.now(UTC)
        document.index_started_at = None
        document.index_heartbeat_at = None
        document.index_completed_at = None
        document.index_recovery_count = 0

        # 4. 在同一个 Session 中新增发件箱事件。payload 是将来发送给 Celery
        #    的参数快照；aggregate 字段用于活动事件去重和审计查询。
        self.outbox_event_repository.add_pending_event(
            event_type=OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
            aggregate_type=OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
            aggregate_id=document.id,
            payload={"document_id": document.id},
        )

        # 5. 两个 Repository 由依赖注入传入同一个 AsyncSession，因此这一次
        #    commit 会同时保存文档 PENDING 状态和发件箱事件。任何约束失败都会
        #    回滚两项修改，不会产生半完成状态。
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            # 数据库部分唯一索引是并发场景的最终防线。只有命中该索引才表示
            # 当前文档已经存在等待发布或正在发布的索引事件；其他完整性异常
            # 必须继续抛出，避免被错误包装成“重复提交”。
            if "uq_outbox_events_active_aggregate" in str(exc.orig):
                raise ConflictException("该文档已有等待处理的索引任务") from exc
            raise

        # 6. 重新查询用于返回完整的模块、创建人和切片统计字段。此时任务只是
        #    可靠登记在 PostgreSQL，并不代表 Redis 已收到或索引已经完成。
        queued_document = await self.repository.get_document(
            knowledge_base_id,
            document_id,
        )
        if queued_document is None:
            raise RuntimeError("索引任务提交后无法重新查询文档")
        return self._knowledge_document_read(queued_document)

    async def delete_knowledge_document(
            self,
            project_id: int,
            knowledge_base_id: int,
            document_id: int,
            current_user: User,
    ) -> None:
        """删除知识文档、检索切片并可靠安排原文件清理。

        功能：校验数据权限，软删除文档，删除全文/向量切片，取消活动索引事件，
        并创建一条原始文件删除事件。

        作用：由知识文档删除 API 调用，是前端删除按钮的完整后端业务入口。

        为什么用它：数据库和文件存储不能共享 PostgreSQL 事务，因此先把“需要
        删除文件”写入事务性发件箱。数据库提交后即使应用崩溃，Celery 发布器仍
        能继续清理文件；直接在请求中删文件会产生数据库与磁盘不一致窗口。
        """

        # 1. 先走知识库数据权限，避免仅凭可猜测的 document_id 删除其他项目文件。
        knowledge_base = (
            await self.knowledge_base_repository.get_accessible_knowledge_base(
                project_id,
                knowledge_base_id,
                current_user,
            )
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权操作")

        # 2. 对目标文档加行锁。找不到时统一返回 404，也不会暴露它是否属于其他
        #    知识库或是否已经被删除。
        document = await self.repository.get_document_for_deletion(
            knowledge_base_id,
            document_id,
        )
        if document is None:
            raise NotFoundException("知识文档不存在或已删除")
        if not document.object_key:
            raise BadRequestException("知识文档缺少存储对象键，无法完成文件清理")

        # 3. 先暂存受信任的对象键。文档软删除后仍保留该字段用于审计，但后台
        #    删除任务只读取发件箱中的参数快照，不依赖后续再次查询文档。
        object_key = document.object_key

        # 4. 在当前事务中让文档立即退出列表和检索，并阻止旧索引任务继续写入。
        await self.repository.prepare_document_deletion(document)

        # 5. 同一事务登记文件清理事件。发布器只允许该固定事件映射到固定 Celery
        #    任务，不能把数据库中的任意字符串当作可执行任务。
        self.outbox_event_repository.add_pending_event(
            event_type=OutboxEventType.KNOWLEDGE_DOCUMENT_FILE_DELETE.value,
            aggregate_type=OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
            aggregate_id=document.id,
            payload={
                "document_id": document.id,
                "object_key": object_key,
            },
        )

        # 6. 一次提交以上全部数据库变化；任何一步失败都会整体回滚。
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

    async def preview_document(self, project_id: int, knowledge_base_id: int, document_id: int,
                               current_user: User) -> KnowledgeDocumentPreview:
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权操作")
        knowledge_document = await self.repository.get_document(
            knowledge_base.id,
            document_id
        )
        if knowledge_document is None:
            raise NotFoundException("文档不存在或无权操作")
        if knowledge_document.object_key is None:
            raise BadRequestException("没有原始文件，拒绝预览")
        content = self.document_storage.stream_file(knowledge_document.object_key)
        return KnowledgeDocumentPreview(
            content=content,
            mime_type=(
                knowledge_document.mime_type
                or "application/octet-stream"
            ),
            filename=(
                    knowledge_document.original_filename
                    or knowledge_document.title
            ),
        )
