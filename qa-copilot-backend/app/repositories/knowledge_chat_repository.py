"""知识问答会话、消息和记忆摘要的数据访问层。"""

from datetime import datetime

from sqlalchemy import exists, func, select, update

from app.core.constants import KnowledgeChatMemoryStatus, KnowledgeChatMessageStatus, KnowledgeChatSessionStatus
from app.models import KnowledgeChatMemorySummary, KnowledgeChatMessage, KnowledgeChatSession
from app.repositories.base_repository import BaseRepository


class KnowledgeChatRepository(BaseRepository):
    """知识问答会话、消息和记忆摘要的数据访问层。"""

    async def list_session(
        self,
        project_id: int,
        knowledge_base_id: int,
        user_id: int,
        status: KnowledgeChatSessionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[KnowledgeChatSession], int]:
        conditions = [
            KnowledgeChatSession.project_id == project_id,
            KnowledgeChatSession.knowledge_base_id == knowledge_base_id,
            KnowledgeChatSession.user_id == user_id,
            KnowledgeChatSession.deleted_at.is_(None),
        ]
        if status is not None:
            conditions.append(KnowledgeChatSession.status == status.value)
        total_statement = select(func.count()).select_from(KnowledgeChatSession).where(*conditions)
        total = await self.session.scalar(total_statement)
        session_statement = (
            select(KnowledgeChatSession)
            .where(*conditions)
            .order_by(
                KnowledgeChatSession.last_message_at.desc().nulls_first(),
                KnowledgeChatSession.created_at.desc(),
                KnowledgeChatSession.id.desc(),
            )
            .offset((current - 1) * size)
            .limit(size)
        )
        sessions = list((await self.session.scalars(session_statement)).all())
        return sessions, total or 0

    async def get_owned_session(self, session_id: int, user_id: int) -> KnowledgeChatSession | None:
        conditions = [
            KnowledgeChatSession.id == session_id,
            KnowledgeChatSession.user_id == user_id,
            KnowledgeChatSession.deleted_at.is_(None),
        ]
        session_statement = select(KnowledgeChatSession).where(*conditions)
        return await self.session.scalar(session_statement)

    async def list_audit_sessions(
        self,
        project_id: int,
        knowledge_base_id: int | None,
        user_id: int | None,
        status: KnowledgeChatSessionStatus | None,
        current: int,
        size: int,
    ) -> tuple[list[KnowledgeChatSession], int]:
        """审计查询不套用当前用户所有权，但始终限制在一个项目内。"""
        conditions = [
            KnowledgeChatSession.project_id == project_id,
            KnowledgeChatSession.deleted_at.is_(None),
        ]
        if knowledge_base_id is not None:
            conditions.append(KnowledgeChatSession.knowledge_base_id == knowledge_base_id)
        if user_id is not None:
            conditions.append(KnowledgeChatSession.user_id == user_id)
        if status is not None:
            conditions.append(KnowledgeChatSession.status == status.value)
        total = int(await self.session.scalar(select(func.count(KnowledgeChatSession.id)).where(*conditions)) or 0)
        records = list(
            (
                await self.session.scalars(
                    select(KnowledgeChatSession)
                    .where(*conditions)
                    .order_by(
                        KnowledgeChatSession.last_message_at.desc().nulls_last(),
                        KnowledgeChatSession.id.desc(),
                    )
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return records, total

    async def get_project_session(self, project_id: int, session_id: int) -> KnowledgeChatSession | None:
        return await self.session.scalar(
            select(KnowledgeChatSession).where(
                KnowledgeChatSession.project_id == project_id,
                KnowledgeChatSession.id == session_id,
                KnowledgeChatSession.deleted_at.is_(None),
            )
        )

    async def list_messages(
        self,
        session_id: int,
        before_id: int | None,
        limit: int,
    ) -> tuple[list[KnowledgeChatMessage], bool]:
        conditions = [KnowledgeChatMessage.session_id == session_id]
        if before_id is not None:
            conditions.append(KnowledgeChatMessage.id < before_id)
        statement = (
            select(KnowledgeChatMessage).where(*conditions).order_by(KnowledgeChatMessage.id.desc()).limit(limit + 1)
        )
        messages = list((await self.session.scalars(statement)).all())
        has_more = len(messages) > limit
        messages = messages[:limit]
        #  反转列表
        messages.reverse()
        return messages, has_more

    async def list_recent_successful_messages(
        self,
        session_id: int,
        before_message_id: int,
        limit: int,
    ) -> list[KnowledgeChatMessage]:
        conditions = [
            KnowledgeChatMessage.session_id == session_id,
            KnowledgeChatMessage.id < before_message_id,
            KnowledgeChatMessage.status == KnowledgeChatMessageStatus.SUCCESS.value,
        ]
        statement = (
            select(KnowledgeChatMessage).where(*conditions).order_by(KnowledgeChatMessage.id.desc()).limit(limit)
        )
        messages = list((await self.session.scalars(statement)).all())
        messages.reverse()
        return messages

    async def touch_session(self, session_id: int, last_message_at: datetime, token_delta: int) -> int | None:
        """
        最近消息时间
        未压缩 Token 总数
        更新时间
        """
        statement = (
            update(KnowledgeChatSession)
            .where(KnowledgeChatSession.id == session_id, KnowledgeChatSession.deleted_at.is_(None))
            .values(
                last_message_at=last_message_at,
                unsummarized_token_count=KnowledgeChatSession.unsummarized_token_count + token_delta,
                updated_at=last_message_at,
            )
            .returning(KnowledgeChatSession.unsummarized_token_count)
        )
        unsummarized_token_count = await self.session.scalar(statement)
        return unsummarized_token_count

    async def get_message(
        self,
        session_id: int,
        message_id: int,
    ) -> KnowledgeChatMessage | None:
        statement = select(KnowledgeChatMessage).where(
            KnowledgeChatMessage.session_id == session_id, KnowledgeChatMessage.id == message_id
        )
        return await self.session.scalar(statement)

    async def get_session_for_memory(
        self,
        session_id: int,
    ) -> KnowledgeChatSession | None:
        statement = (
            select(KnowledgeChatSession)
            .where(KnowledgeChatSession.id == session_id, KnowledgeChatSession.deleted_at.is_(None))
            .with_for_update()
        )
        return await self.session.scalar(statement)

    async def list_successful_messages_after(
        self,
        session_id: int,
        #
        after_message_id: int | None,
        limit: int,
    ) -> list[KnowledgeChatMessage]:
        conditions = [
            KnowledgeChatMessage.session_id == session_id,
            KnowledgeChatMessage.status == KnowledgeChatMessageStatus.SUCCESS.value,
        ]
        if after_message_id is not None:
            # 查询摘要游标之后尚未摘要的新消息
            conditions.append(KnowledgeChatMessage.id > after_message_id)
        messages = await self.session.scalars(
            select(KnowledgeChatMessage).where(*conditions).order_by(KnowledgeChatMessage.id.asc()).limit(limit)
        )
        return list(messages)

    async def get_memory_summary_by_range(
        self,
        session_id: int,
        from_message_id: int,
        to_message_id: int,
    ) -> KnowledgeChatMemorySummary | None:
        conditions = [
            KnowledgeChatMemorySummary.session_id == session_id,
            KnowledgeChatMemorySummary.from_message_id == from_message_id,
            KnowledgeChatMemorySummary.to_message_id == to_message_id,
        ]
        statement = select(KnowledgeChatMemorySummary).where(*conditions)
        return await self.session.scalar(statement)

    async def update_session_after_memory_compression(
        self,
        session_id: int,
        expected_memory_version: int,
        expected_last_summarized_message_id: int | None,
        to_message_id: int,
        compressed_token_count: int,
        updated_at: datetime,
    ) -> bool:
        """记忆摘要生成成功后，更新会话中的“历史压缩进度”。

        这个方法一次完成三件事：
        1. 记录本次摘要已经处理到哪一条消息；
        2. 会话记忆版本加一；
        3. 从“尚未压缩 Token”中扣掉本次已经摘要的原始消息 Token。

        为什么不能先在 Python 中算好新值再保存：
        生成摘要和向量可能需要十几秒，这段时间用户仍可能发送新消息。
        数据库里的未压缩 Token 会继续增加，而任务开始时读取的 Python 对象
        已经是旧数据。这里让数据库直接使用最新值做减法，才不会把新消息
        增加的 Token 覆盖掉。

        expected_memory_version 和 expected_last_summarized_message_id 是任务
        开始时记下的旧值。最终保存前再次比较，可以确认没有其他任务先完成
        了同一会话的压缩。如果数据已经变化，本方法返回 False，不覆盖别人
        已经保存的结果。

        本方法不执行 commit。Service 还要同时把摘要状态改成 READY，这两项
        修改需要由 Service 一起提交，避免只更新了其中一项。
        """

        conditions = [
            # 只更新当前任务处理的、尚未被删除的会话。
            KnowledgeChatSession.id == session_id,
            KnowledgeChatSession.deleted_at.is_(None),
            # 只有数据库中的版本仍等于任务开始时的版本，才说明没有其他
            # 压缩任务抢先完成。
            KnowledgeChatSession.memory_version == expected_memory_version,
            # 当前剩余 Token 必须够扣，防止结果变成负数。
            KnowledgeChatSession.unsummarized_token_count >= compressed_token_count,
        ]

        # last_summarized_message_id 可以理解成书签：它记录“历史消息已经摘要
        # 到哪一条”。第一次压缩时没有书签，所以数据库中必须还是 NULL；
        # 后续压缩时，数据库中的书签必须和任务开始时看到的一样。
        if expected_last_summarized_message_id is None:
            conditions.append(KnowledgeChatSession.last_summarized_message_id.is_(None))
        else:
            conditions.append(KnowledgeChatSession.last_summarized_message_id == expected_last_summarized_message_id)

        statement = (
            update(KnowledgeChatSession)
            .where(*conditions)
            .values(
                # 把“已摘要到哪条消息”的书签更新为本次最后一条消息。
                last_summarized_message_id=to_message_id,
                # 每成功完成一次压缩，版本号加一。
                memory_version=KnowledgeChatSession.memory_version + 1,
                # 直接使用数据库此刻的最新值减去本次压缩量。模型生成期间
                # 新消息增加的 Token 会被保留下来。
                unsummarized_token_count=(KnowledgeChatSession.unsummarized_token_count - compressed_token_count),
                updated_at=updated_at,
            )
            # 更新成功会返回会话 ID；条件不满足则返回 None。
            .returning(KnowledgeChatSession.id)
        )

        updated_session_id = await self.session.scalar(statement)
        return updated_session_id is not None

    async def has_ready_memory_summaries(
        self,
        session_id: int,
    ) -> bool:
        """当前会话是否至少存在一条可用于检索的长期记忆"""
        statement = select(
            exists().where(
                KnowledgeChatMemorySummary.session_id == session_id,
                KnowledgeChatMemorySummary.status == KnowledgeChatMemoryStatus.READY.value,
                KnowledgeChatMemorySummary.embedding.is_not(None),
            )
        )
        return bool(await self.session.scalar(statement))

    async def list_relevant_memory_summaries(
        self,
        session_id: int,
        query_vector: list[float],
        limit: int,
    ) -> list[KnowledgeChatMemorySummary]:
        """
        记忆摘要向量检索：问题向量和历史摘要向量比较
            1. 计算每条摘要向量与问题向量的余弦距离
            2. 只查询当前 session_id 下可用且有向量的摘要
            3. 按距离从小到大排序
            4. 限制返回数量并转换成 list
        """
        distance_expression = KnowledgeChatMemorySummary.embedding.cosine_distance(query_vector)
        conditions = [
            KnowledgeChatMemorySummary.session_id == session_id,
            KnowledgeChatMemorySummary.status == KnowledgeChatMemoryStatus.READY.value,
            KnowledgeChatMemorySummary.embedding.is_not(None),
        ]

        statement = (
            select(KnowledgeChatMemorySummary).where(*conditions).order_by(distance_expression.asc()).limit(limit)
        )
        summaries = await self.session.scalars(statement)
        return list(summaries)
