from datetime import datetime

from sqlalchemy import and_, delete, exists, func, insert, or_, select, update
from sqlalchemy.orm import selectinload, with_expression

from app.core.constants import (
    KnowledgeDocumentParseStatus,
    KnowledgeDocumentType,
    OutboxAggregateType,
    OutboxEventStatus,
    OutboxEventType,
)
from app.models import (
    AIModel,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    KnowledgeDocumentChunkStaging,
    OutboxEvent,
)
from app.models.mixins import utc_now
from app.repositories.base_repository import BaseRepository


class KnowledgeDocumentRepository(BaseRepository):
    async def list_knowledge_documents(
            self,
            knowledge_base_id: int,
            document_type: str | None,
            parse_status: str | None,
            module_id: int | None,
            current: int,
            size: int,
            keyword: str,
    ) -> tuple[list[KnowledgeDocument], int]:
        """按知识库和筛选条件分页查询未删除文档。"""

        # 1. 创建 conditions 列表，先放入两个任何查询都必须满足的条件：
        #    - 文档的 knowledge_base_id 等于当前知识库 ID；
        #    - deleted_at IS NULL，只查询没有被软删除的文档。
        conditions = [
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.deleted_at.is_(None),
        ]
        # 2. keyword 去掉首尾空格后如果仍有内容，向 conditions 添加 OR 条件：
        #    - title 包含关键字；
        #    - original_filename 包含关键字。
        #    `or_()` 表示两个字段满足任意一个即可。
        keyword = keyword.strip()
        if keyword:
            conditions.append(
                or_(
                    KnowledgeDocument.title.contains(keyword),
                    KnowledgeDocument.original_filename.contains(keyword), )
            )
        # 3. 三个可选筛选参数分别判断：
        #    - document_type 不是 None 时，添加文档类型相等条件；
        #    - parse_status 不是 None 时，添加解析状态相等条件；
        #    - module_id 不是 None 时，添加所属模块相等条件。
        if document_type is not None:
            conditions.append(KnowledgeDocument.document_type == document_type)
        if parse_status is not None:
            conditions.append(KnowledgeDocument.parse_status == parse_status)
        if module_id is not None:
            conditions.append(KnowledgeDocument.module_id == module_id)
        # 4. 使用下面这种结构查询符合相同 conditions 的总记录数：
        #    `select(func.count(KnowledgeDocument.id)).where(*conditions)`。
        #    `scalar()` 只取 SQL 查询结果的第一个值；数据库返回 None 时用 0。
        total_query = select(func.count(KnowledgeDocument.id)).where(*conditions)
        total = await self.session.scalar(total_query) or 0
        # 5. 创建一个“相关子查询”，统计当前每篇文档对应的切片数量：
        #    - 从 KnowledgeDocumentChunk 统计 id 数量；
        #    - 条件是 chunk.document_id == 外层 document.id；
        #    - correlate(KnowledgeDocument) 表明它引用外层正在查询的文档；
        #    - scalar_subquery() 把统计查询变成可放进外层 SELECT 的单个值。
        #
        #    需要组合使用的方法：
        #    select(func.count(...)).where(...).correlate(...).scalar_subquery()
        chunk_count_subquery = select(func.count(KnowledgeDocumentChunk.id)).where(
            KnowledgeDocumentChunk.document_id == KnowledgeDocument.id
        ).correlate(KnowledgeDocument).scalar_subquery()

        # 6. 创建文档分页查询 statement：
        #    - `select(KnowledgeDocument).where(*conditions)` 应用筛选；
        #    - `with_expression()` 把第 5 步统计值装入 document.chunk_count；
        #    - `selectinload()` 预加载 module 和 creator，转换 VO 时不会再临时查询；
        #    - 按 updated_at、id 倒序，最新文档排在前面；
        #    - offset 为 `(current - 1) * size`；
        #    - limit 为 `size`。
        statement = (((select(KnowledgeDocument)
                       .options(
            with_expression(KnowledgeDocument.chunk_count, chunk_count_subquery),
            selectinload(KnowledgeDocument.module),
            selectinload(KnowledgeDocument.creator)
        )
                       .where(*conditions))
                      .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc()))
                     .offset((current - 1) * size)
                     .limit(size))
        # 7. 执行分页 statement：
        #    `await self.session.scalars(statement)` 返回实体标量结果；
        #    `.all()` 取出全部当前页记录，再用 list() 转成明确的列表。
        documents = list((await self.session.scalars(statement)).all())
        # 8. 返回 `(documents, total)`。
        return documents, total

    async def get_document(
            self,
            knowledge_base_id: int,
            document_id: int,
    ) -> KnowledgeDocument | None:
        """查询知识库中的一篇未删除文档，并附带列表和详情需要的关联数据。"""

        # 1. 创建一个“相关子查询”，统计当前文档拥有多少个切片：
        #    - 从 KnowledgeDocumentChunk 表统计 id 数量；
        #    - chunk.document_id 必须等于外层正在查询的 document.id；
        #    - correlate(KnowledgeDocument) 表示子查询引用外层文档；
        #    - scalar_subquery() 把统计查询转换成一个可以放入 SELECT 的值。
        chunk_count_subquery = (
            select(func.count(KnowledgeDocumentChunk.id))
            .where(KnowledgeDocumentChunk.document_id == KnowledgeDocument.id)
            .correlate(KnowledgeDocument)
            .scalar_subquery()
        )
        # 2. 创建查询 statement，以 KnowledgeDocument 实体作为查询目标。
        # 3. 使用 options() 补充查询时需要一起取得的数据：
        #    - with_expression()：把第 1 步的统计结果装入 document.chunk_count；
        #    - selectinload()：预加载 document.module；
        #    - selectinload()：预加载 document.creator。
        #    这样 Service 转换 VO 时就可以直接访问模块名称、创建人和切片数量。

        # 4. 使用 where() 添加三个必须同时满足的条件：
        #    - document.knowledge_base_id == knowledge_base_id，防止查询到其他知识库的文档；
        #    - document.id == document_id，定位目标文档；
        #    - document.deleted_at IS NULL，排除已经软删除的文档。
        statement = select(KnowledgeDocument).options(
            with_expression(KnowledgeDocument.chunk_count, chunk_count_subquery),
            selectinload(KnowledgeDocument.module),
            selectinload(KnowledgeDocument.creator)
        ).where(KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.deleted_at.is_(None), )
        knowledge_document = await self.session.scalar(statement)

        # 5. 使用 `await self.session.scalar(statement)` 执行查询并直接返回结果：
        #    - 查询到时返回 KnowledgeDocument；
        #    - 查询不到时返回 None。
        return knowledge_document

    async def get_by_sha256(
            self,
            knowledge_base_id: int,
            sha256: str,
    ) -> KnowledgeDocument | None:
        """查询当前知识库是否已经存在内容完全相同的未删除文档。"""

        # 这个方法用于“上传文档”业务中的哈希去重。
        # 服务层读取文件内容并计算 SHA-256 后，会先调用本方法：
        # - 查询到文档：说明同一个知识库已经上传过内容完全相同的文件；
        # - 返回 None：说明不存在相同文件，可以继续保存文件和创建文档记录。

        # 1. 创建以 KnowledgeDocument 为查询目标的 statement。

        # 2. 使用 where() 添加三个必须同时满足的条件：
        #    - knowledge_base_id 等于传入的知识库 ID；
        #    - sha256 等于传入的文件哈希；
        #    - deleted_at IS NULL，只判断仍然有效的文档。
        #    已经软删除的旧文档不应该阻止用户重新上传。

        # 3. 这里不需要 selectinload() 和 with_expression()：
        #    本方法只判断重复文件是否存在，不会立即转换成前端 VO，
        #    因此没有必要额外查询模块、创建人和切片数量。
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.sha256 == sha256,
            KnowledgeDocument.deleted_at.is_(None),
        )
        # 4. 使用 `await self.session.scalar(statement)` 执行查询并返回：
        #    - 存在相同文件时返回对应的 KnowledgeDocument；
        #    - 不存在时返回 None。
        return await self.session.scalar(statement)

    async def get_document_for_index(
            self,
            document_id: int,
            *,
            lock: bool = False,
    ) -> KnowledgeDocument | None:
        """读取索引任务需要的文档、知识库、Embedding 模型和服务商。"""

        statement = (
            select(KnowledgeDocument)
            .options(
                selectinload(KnowledgeDocument.knowledge_base)
                .selectinload(KnowledgeBase.embedding_model)
                .selectinload(AIModel.provider)
            )
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def claim_document_for_index(
            self,
            document_id: int,
            task_id: str,
    ) -> KnowledgeDocument | None:
        """锁定文档并把可执行任务原子推进到 PARSING，重复任务返回 None。"""
        document = await self.get_document_for_index(document_id, lock=True)
        if document is None or document.parse_status not in {"PENDING", "FAILED"}:
            await self.rollback()
            return None

        now = utc_now()
        document.parse_status = "PARSING"
        document.error_message = None
        document.index_task_id = task_id
        document.index_started_at = now
        document.index_heartbeat_at = now
        document.index_completed_at = None

        # 新任务取得文档执行权后，清除旧任务崩溃时可能遗留的暂存切片。
        # 正式切片仍然保留，直到新任务所有批次成功并原子发布。
        await self.session.execute(
            delete(KnowledgeDocumentChunkStaging).where(
                KnowledgeDocumentChunkStaging.document_id == document_id
            )
        )
        await self.commit()
        return document

    async def mark_parse_status(
            self,
            document_id: int,
            task_id: str,
            status: str,
            error_message: str | None = None,
    ) -> bool:
        """仅由仍持有当前任务编号的 Worker 更新文档处理状态。"""

        values: dict[str, object] = {
            "parse_status": status,
            "error_message": error_message,
        }
        now = utc_now()
        if status in {
            KnowledgeDocumentParseStatus.PARSING.value,
            KnowledgeDocumentParseStatus.INDEXING.value,
        }:
            values["index_heartbeat_at"] = now
        if status in {
            KnowledgeDocumentParseStatus.READY.value,
            KnowledgeDocumentParseStatus.FAILED.value,
        }:
            values["index_heartbeat_at"] = now
            values["index_completed_at"] = now

        updated_id = await self.session.scalar(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.index_task_id == task_id,
            )
            .values(**values)
            .returning(KnowledgeDocument.id)
        )
        await self.commit()
        return updated_id is not None

    async def touch_index_heartbeat(
            self,
            document_id: int,
            task_id: str,
    ) -> bool:
        """更新正在执行的文档索引心跳。

        功能：仅当文档仍处于 ``PARSING`` 或 ``INDEXING`` 时刷新心跳时间。

        作用：Worker 在耗时的解析和 Embedding 批次之间调用，供补偿扫描判断
        任务是在正常运行还是已经卡死。

        为什么用它：仅依赖状态更新时间会把长时间运行的正常任务误判为卡死；
        独立心跳能表示 Worker 最近仍有进展，同时条件更新避免复活已结束任务。
        """

        updated_id = await self.session.scalar(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.index_task_id == task_id,
                KnowledgeDocument.parse_status.in_(
                    (
                        KnowledgeDocumentParseStatus.PARSING.value,
                        KnowledgeDocumentParseStatus.INDEXING.value,
                    )
                ),
            )
            .values(index_heartbeat_at=utc_now())
            .returning(KnowledgeDocument.id)
        )
        await self.commit()
        return updated_id is not None

    async def replace_chunks(
            self,
            document_id: int,
            task_id: str,
            chunks: list[KnowledgeDocumentChunk],
    ) -> bool:
        """当前任务仍持有执行权时，原子替换切片并标记 READY。"""

        owned_document = await self.session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.index_task_id == task_id,
                KnowledgeDocument.parse_status
                == KnowledgeDocumentParseStatus.INDEXING.value,
            )
            .with_for_update()
        )
        if owned_document is None:
            await self.rollback()
            return False

        await self.session.execute(
            delete(KnowledgeDocumentChunk).where(
                KnowledgeDocumentChunk.document_id == document_id
            )
        )
        self.session.add_all(chunks)
        await self.flush()

        # search_vector 是 PostgreSQL 生成列，会根据 section_title 和 content
        # 自动计算。这里不能显式写入 NULL 或手工 UPDATE。
        await self.session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .values(
                parse_status="READY",
                error_message=None,
                index_heartbeat_at=utc_now(),
                index_completed_at=utc_now(),
            )
        )
        await self.commit()
        return True

    async def append_staged_chunks(
        self,
        document_id: int,
        task_id: str,
        chunks: list[KnowledgeDocumentChunkStaging],
    ) -> bool:
        """把一个已完成向量化的切片批次写入暂存表。

        功能：确认当前 Worker 仍持有文档任务编号后，提交一小批暂存切片。
        作用：索引 Service 每完成一次 Embedding 调用就调用本方法，使 Python
        内存中最多保留一个批次，而正式索引在全部成功前保持不变。
        为什么用它：每批独立提交可以及时释放 ORM 对象和数据库事务；对文档行
        加锁则让所有权检查和本批写入处于同一事务，补偿任务不能在中间换走
        ``task_id``。替代方案是一次保存全部切片，但会使内存随文档大小增长。
        """

        owned_document_id = await self.session.scalar(
            select(KnowledgeDocument.id)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.index_task_id == task_id,
                KnowledgeDocument.parse_status
                == KnowledgeDocumentParseStatus.INDEXING.value,
            )
            .with_for_update()
        )
        if owned_document_id is None:
            await self.rollback()
            return False

        self.session.add_all(chunks)
        await self.commit()
        return True

    async def publish_staged_chunks(
        self,
        document_id: int,
        task_id: str,
        expected_chunk_count: int,
    ) -> bool:
        """把完整暂存结果原子发布成正式知识索引。

        功能：校验任务所有权和暂存数量，删除旧正式切片，复制新切片，清理暂存
        数据并把文档标记为 READY。
        作用：这是流式索引流水线唯一会改变线上可检索切片的步骤。
        为什么用它：上述修改在一个 PostgreSQL 事务内完成，其他查询只能看到
        “完整旧版本”或“完整新版本”，看不到替换到一半的状态。仅靠 Python
        依次执行无法在进程崩溃时提供该原子性。
        """

        document = await self.session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.index_task_id == task_id,
                KnowledgeDocument.parse_status
                == KnowledgeDocumentParseStatus.INDEXING.value,
            )
            .with_for_update()
        )
        if document is None:
            await self.rollback()
            return False

        staged_count = await self.session.scalar(
            select(func.count(KnowledgeDocumentChunkStaging.id)).where(
                KnowledgeDocumentChunkStaging.document_id == document_id,
                KnowledgeDocumentChunkStaging.task_id == task_id,
            )
        )
        if staged_count != expected_chunk_count or expected_chunk_count <= 0:
            await self.rollback()
            raise RuntimeError(
                "暂存切片数量与索引任务统计不一致，拒绝发布不完整索引"
            )

        await self.session.execute(
            delete(KnowledgeDocumentChunk).where(
                KnowledgeDocumentChunk.document_id == document_id
            )
        )

        # search_vector 是正式表的 PostgreSQL 生成列，故意不出现在复制字段中；
        # INSERT 时数据库会根据 section_title 和 content 自动重新计算。
        await self.session.execute(
            insert(KnowledgeDocumentChunk).from_select(
                [
                    "document_id",
                    "chunk_index",
                    "content",
                    "token_count",
                    "page_no",
                    "section_title",
                    "embedding_model_id",
                    "embedding_dimensions",
                    "index_version",
                    "metadata",
                    "embedding",
                    "created_at",
                ],
                select(
                    KnowledgeDocumentChunkStaging.document_id,
                    KnowledgeDocumentChunkStaging.chunk_index,
                    KnowledgeDocumentChunkStaging.content,
                    KnowledgeDocumentChunkStaging.token_count,
                    KnowledgeDocumentChunkStaging.page_no,
                    KnowledgeDocumentChunkStaging.section_title,
                    KnowledgeDocumentChunkStaging.embedding_model_id,
                    KnowledgeDocumentChunkStaging.embedding_dimensions,
                    KnowledgeDocumentChunkStaging.index_version,
                    KnowledgeDocumentChunkStaging.chunk_metadata,
                    KnowledgeDocumentChunkStaging.embedding,
                    KnowledgeDocumentChunkStaging.created_at,
                )
                .where(
                    KnowledgeDocumentChunkStaging.document_id == document_id,
                    KnowledgeDocumentChunkStaging.task_id == task_id,
                )
                .order_by(KnowledgeDocumentChunkStaging.chunk_index),
            )
        )
        await self.session.execute(
            delete(KnowledgeDocumentChunkStaging).where(
                KnowledgeDocumentChunkStaging.document_id == document_id,
                KnowledgeDocumentChunkStaging.task_id == task_id,
            )
        )

        now = utc_now()
        document.parse_status = KnowledgeDocumentParseStatus.READY.value
        document.error_message = None
        document.index_heartbeat_at = now
        document.index_completed_at = now
        await self.commit()
        return True

    async def discard_staged_chunks(
        self,
        document_id: int,
        task_id: str,
    ) -> None:
        """删除失败任务留下的暂存切片，不影响仍在线上的正式索引。"""

        await self.session.execute(
            delete(KnowledgeDocumentChunkStaging).where(
                KnowledgeDocumentChunkStaging.document_id == document_id,
                KnowledgeDocumentChunkStaging.task_id == task_id,
            )
        )
        await self.commit()

    async def get_document_for_deletion(
            self,
            knowledge_base_id: int,
            document_id: int,
    ) -> KnowledgeDocument | None:
        """锁定一篇待删除的知识文档。

        功能：按知识库和文档 ID 查询未删除文档，并取得数据库行锁。

        作用：删除 Service 在清理切片、终止活动索引事件和登记文件清理事件前
        调用，保证同一篇文档不会被两个请求同时删除或重新提交索引。

        为什么用它：删除包含多项数据库修改，``FOR UPDATE`` 可以把并发操作串行
        化；如果只使用普通查询，删除与重新索引可能同时修改同一篇文档。
        """

        return await self.session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
            .with_for_update()
        )

    async def prepare_document_deletion(
            self,
            document: KnowledgeDocument,
    ) -> None:
        """在当前事务中软删除文档并清除可检索数据。

        功能：设置文档删除时间、撤销旧 Worker 的任务所有权、删除全部切片，并把
        尚未发布完成的索引事件标记为失败。

        作用：这是数据库侧的完整删除动作。调用方随后在同一事务中登记原始文件
        清理事件并统一提交。

        为什么用它：文档使用软删除保留审计元数据，数据库级 ``ON DELETE
        CASCADE`` 不会触发，所以切片必须显式删除；清空 ``index_task_id`` 相当于
        撤销旧 Worker 的栅栏令牌，可阻止它在删除后重新写入向量。
        """

        now = utc_now()
        document.deleted_at = now
        document.index_task_id = None
        document.index_heartbeat_at = None
        document.index_completed_at = now

        # 切片同时包含全文检索字段和向量，删除记录即可让该文档立即退出检索。
        await self.session.execute(
            delete(KnowledgeDocumentChunk).where(
                KnowledgeDocumentChunk.document_id == document.id
            )
        )
        await self.session.execute(
            delete(KnowledgeDocumentChunkStaging).where(
                KnowledgeDocumentChunkStaging.document_id == document.id
            )
        )

        # PUBLISHED/FAILED 是历史审计记录，继续保留；只终止仍可能产生新索引任务
        # 的活动事件。即使发布器已经把任务送入 Redis，Worker 领取时也会因为文档
        # 已软删除而停止。
        await self.session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.event_type
                == OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                OutboxEvent.aggregate_type
                == OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                OutboxEvent.aggregate_id == document.id,
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.PROCESSING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                ),
            )
            .values(
                status=OutboxEventStatus.FAILED.value,
                locked_at=None,
                locked_by=None,
                last_error="知识文档已删除，索引事件已取消",
                updated_at=now,
            )
        )

    async def lock_stale_index_documents(
            self,
            *,
            pending_before: datetime,
            processing_before: datetime,
            limit: int,
    ) -> list[KnowledgeDocument]:
        """锁定已提交但长期未推进的知识文档。

        功能：查找没有活动发件箱事件的超时 ``PENDING`` 文档，以及心跳超时的
        ``PARSING/INDEXING`` 文档，并用 ``SKIP LOCKED`` 批量认领。

        作用：供后台补偿 Service 决定重新排队还是达到上限后标记最终失败。

        为什么用它：``index_queued_at IS NOT NULL`` 排除了只上传未提交的文档；
        ``NOT EXISTS`` 活动发件箱事件避免重复补建；行锁允许多扫描器安全并行。
        """

        active_event_exists = exists(
            select(OutboxEvent.id).where(
                OutboxEvent.event_type
                == OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                OutboxEvent.aggregate_type
                == OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                OutboxEvent.aggregate_id == KnowledgeDocument.id,
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.PROCESSING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                ),
            )
        )
        last_processing_activity = func.coalesce(
            KnowledgeDocument.index_heartbeat_at,
            KnowledgeDocument.index_started_at,
            KnowledgeDocument.updated_at,
        )
        statement = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.deleted_at.is_(None),
                or_(
                    and_(
                        KnowledgeDocument.parse_status
                        == KnowledgeDocumentParseStatus.PENDING.value,
                        KnowledgeDocument.index_queued_at.is_not(None),
                        KnowledgeDocument.index_queued_at <= pending_before,
                        ~active_event_exists,
                    ),
                    and_(
                        KnowledgeDocument.parse_status.in_(
                            (
                                KnowledgeDocumentParseStatus.PARSING.value,
                                KnowledgeDocumentParseStatus.INDEXING.value,
                            )
                        ),
                        last_processing_activity <= processing_before,
                    ),
                ),
            )
            .order_by(KnowledgeDocument.updated_at, KnowledgeDocument.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.session.scalars(statement)).all())

    async def lock_documents_requiring_reindex(
            self,
            *,
            embedding_dimensions: int,
            index_version: int,
            limit: int,
    ) -> list[KnowledgeDocument]:
        """锁定索引元数据与知识库当前配置不兼容的文档。

        功能：从启用的知识库中查找 ``READY`` 文档；没有切片，或者任一切片的
        Embedding 模型、维度、索引版本不匹配时，将文档选为待重建对象。

        作用：供周期后台任务分批安排全量重建，既处理管理员切换 Embedding
        模型，也处理应用发布后索引版本升级。

        为什么用它：在知识库更新接口内一次处理所有文档会让请求耗时和数据量
        线性增长。数据库分批扫描配合 ``FOR UPDATE SKIP LOCKED``，可以限制每轮
        压力，也允许多个扫描实例安全处理不同文档。
        """

        has_any_chunk = exists(
            select(KnowledgeDocumentChunk.id).where(
                KnowledgeDocumentChunk.document_id == KnowledgeDocument.id
            )
        )
        has_incompatible_chunk = exists(
            select(KnowledgeDocumentChunk.id).where(
                KnowledgeDocumentChunk.document_id == KnowledgeDocument.id,
                or_(
                    KnowledgeDocumentChunk.embedding_model_id.is_distinct_from(
                        KnowledgeBase.embedding_model_id
                    ),
                    KnowledgeDocumentChunk.embedding_dimensions
                    != embedding_dimensions,
                    KnowledgeDocumentChunk.index_version != index_version,
                ),
            )
        )
        active_index_event_exists = exists(
            select(OutboxEvent.id).where(
                OutboxEvent.event_type
                == OutboxEventType.KNOWLEDGE_DOCUMENT_INDEX.value,
                OutboxEvent.aggregate_type
                == OutboxAggregateType.KNOWLEDGE_DOCUMENT.value,
                OutboxEvent.aggregate_id == KnowledgeDocument.id,
                OutboxEvent.status.in_(
                    (
                        OutboxEventStatus.PENDING.value,
                        OutboxEventStatus.PROCESSING.value,
                        OutboxEventStatus.RETRY.value,
                    )
                ),
            )
        )

        statement = (
            select(KnowledgeDocument)
            .join(
                KnowledgeBase,
                KnowledgeBase.id == KnowledgeDocument.knowledge_base_id,
            )
            .where(
                KnowledgeBase.enabled.is_(True),
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeDocument.parse_status
                == KnowledgeDocumentParseStatus.READY.value,
                or_(~has_any_chunk, has_incompatible_chunk),
                ~active_index_event_exists,
            )
            .order_by(KnowledgeDocument.updated_at, KnowledgeDocument.id)
            .limit(limit)
            .with_for_update(
                skip_locked=True,
                of=KnowledgeDocument,
            )
        )
        return list((await self.session.scalars(statement)).all())

    async def list_project_requirement_documents(self, project_id: int):
        statement = (
            select(KnowledgeDocument)
            .join(KnowledgeBase)
            .where(
                KnowledgeBase.project_id == project_id,
                KnowledgeBase.enabled.is_(True),
                KnowledgeDocument.document_type == KnowledgeDocumentType.REQUIREMENT.value,
                KnowledgeDocument.parse_status == KnowledgeDocumentParseStatus.READY.value,
                KnowledgeDocument.deleted_at.is_(None)
            )
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def get_project_requirement_document(self, project_id: int, document_id: int):
        """查询可关联到需求的来源文档，不要求它已经完成异步解析。

        新建需求时直接上传的文档会先处于 PENDING/PARSING/INDEXING，需求主记录
        需要立即保存该文档 ID。真正执行 AI 拆解时仍由 get_document_for_extraction()
        严格要求 READY，避免读取尚未生成完成的切片。
        """
        statement = (
            select(KnowledgeDocument)
            .join(KnowledgeBase)
            .where(
                KnowledgeBase.project_id == project_id,
                KnowledgeDocument.id == document_id,
                KnowledgeBase.enabled.is_(True),
                KnowledgeDocument.document_type == KnowledgeDocumentType.REQUIREMENT.value,
                KnowledgeDocument.deleted_at.is_(None)
            )
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
        )
        return await self.session.scalar(statement)

    async def get_document_for_extraction(
            self,
            project_id: int,
            document_id: int,
            document_version: int,
    ) -> KnowledgeDocument | None:
        statement = (
            select(KnowledgeDocument)
            .join(KnowledgeBase)
            .options(selectinload(KnowledgeDocument.chunks))
            .where(
                KnowledgeBase.project_id == project_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.version == document_version,
                KnowledgeDocument.parse_status == KnowledgeDocumentParseStatus.READY.value,
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeBase.enabled.is_(True),
                KnowledgeDocument.document_type == KnowledgeDocumentType.REQUIREMENT.value,
            )
        )
        return await self.session.scalar(statement)
