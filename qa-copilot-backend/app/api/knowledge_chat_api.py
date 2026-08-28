from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.service_deps.knowledge_chat import KnowledgeChatServiceDep
from app.api.service_deps.knowledge_chat_audit import KnowledgeChatAuditServiceDep
from app.core.constants import KnowledgeChatSessionStatus, KnowledgeChatStreamEventType
from app.core.deps import CurrentUser, RequestId, require_permission
from app.core.permissions import Permission
from app.exceptions.errors import describe_exception
from app.schemas.api_result import ApiResult, PageResult, success
from app.schemas.camel_model import CamelModel
from app.schemas.dto.knowledge_chat import (
    KnowledgeChatMessageCreateDTO,
    KnowledgeChatSessionCreateDTO,
    KnowledgeChatSessionUpdateDTO,
)
from app.schemas.vo.knowledge_chat import (
    KnowledgeChatMessageCursorVO,
    KnowledgeChatSessionVO,
    KnowledgeChatStreamErrorVO,
)

router = APIRouter(
    prefix="/knowledge-chat",
    tags=["知识问答"],
)


@router.get(
    "/audit/{project_id}/sessions",
    response_model=ApiResult[PageResult[KnowledgeChatSessionVO]],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_AUDIT))],
    summary="独立权限审计项目会话",
)
async def audit_chat_sessions(
    current_user: CurrentUser,
    service: KnowledgeChatAuditServiceDep,
    project_id: int,
    knowledge_base_id: Annotated[int | None, Query(alias="knowledgeBaseId", gt=0)] = None,
    user_id: Annotated[int | None, Query(alias="userId", gt=0)] = None,
    status: KnowledgeChatSessionStatus | None = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResult[PageResult[KnowledgeChatSessionVO]]:
    return success(
        await service.list_sessions(
            project_id,
            current_user,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            status=status,
            current=current,
            size=size,
        )
    )


@router.get(
    "/audit/{project_id}/sessions/{session_id}/messages",
    response_model=ApiResult[KnowledgeChatMessageCursorVO],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_AUDIT))],
    summary="独立权限审计会话消息",
)
async def audit_chat_messages(
    current_user: CurrentUser,
    service: KnowledgeChatAuditServiceDep,
    project_id: int,
    session_id: int,
    before_id: Annotated[int | None, Query(alias="beforeId", ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResult[KnowledgeChatMessageCursorVO]:
    return success(await service.list_messages(project_id, session_id, current_user, before_id, limit))


@router.post(
    "/{project_id}/bases/{knowledge_base_id}/sessions",
    response_model=ApiResult[KnowledgeChatSessionVO],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="创建会话",
)
async def chat_knowledge_sessions(
    current_user: CurrentUser,
    service: KnowledgeChatServiceDep,
    project_id: int,
    knowledge_base_id: int,
    payload: KnowledgeChatSessionCreateDTO,
) -> ApiResult[KnowledgeChatSessionVO]:
    result = await service.create_session(
        current_user=current_user,
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        payload=payload,
    )
    return success(result, "创建会话成功")


@router.get(
    "/{project_id}/bases/{knowledge_base_id}/sessions",
    response_model=ApiResult[PageResult[KnowledgeChatSessionVO]],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="查询当前用户的会话列表",
)
async def get_login_user_session_list(
    current_user: CurrentUser,
    service: KnowledgeChatServiceDep,
    project_id: int,
    knowledge_base_id: int,
    status: KnowledgeChatSessionStatus | None = None,
    current: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResult[PageResult[KnowledgeChatSessionVO]]:
    records, total = await service.get_login_user_session_list(
        current_user=current_user,
        project_id=project_id,
        knowledge_base_id=knowledge_base_id,
        status=status,
        current=current,
        size=size,
    )
    return success(PageResult(current=current, total=total, records=records, size=size))


@router.patch(
    "/sessions/{session_id}",
    response_model=ApiResult[KnowledgeChatSessionVO],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="修改会话标题和状态",
)
async def update_session_title_status(
    current_user: CurrentUser, service: KnowledgeChatServiceDep, session_id: int, payload: KnowledgeChatSessionUpdateDTO
) -> ApiResult[KnowledgeChatSessionVO]:
    result = await service.update_session_title_status(
        current_user=current_user,
        session_id=session_id,
        payload=payload,
    )
    return success(result, "修改成功")


@router.delete(
    "/sessions/{session_id}",
    response_model=ApiResult[None],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="删除会话",
)
async def delete_session(
    current_user: CurrentUser, service: KnowledgeChatServiceDep, session_id: int
) -> ApiResult[None]:
    await service.delete_session(current_user=current_user, session_id=session_id)
    return success(message="会话删除成功")


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ApiResult[KnowledgeChatMessageCursorVO],
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="游标分页查询历史信息",
)
async def get_messages(
    current_user: CurrentUser,
    service: KnowledgeChatServiceDep,
    session_id: int,
    before_id: Annotated[
        int | None,
        Query(alias="beforeId", ge=1),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApiResult[KnowledgeChatMessageCursorVO]:
    """
    含义：
        - records：本次查询到的消息，返回给前端时按时间正序排列。
        - hasMore：是否还有更早的消息。
        - nextCursor：下一次请求作为 beforeId 传回来。
    """
    result = await service.list_messages(session_id, current_user, before_id, limit)
    return success(result)


def format_sse_event(
    event_type: KnowledgeChatStreamEventType,
    data: CamelModel,
) -> str:
    """把事件类型和 Pydantic VO 转换为 SSE 标准文本。"""

    # STATUS 转换成前端监听的 status。
    event_name = event_type.value.lower()

    # by_alias=True 将 assistant_message 转换成 assistantMessage。
    json_data = data.model_dump_json(by_alias=True)

    # SSE 固定格式：
    # event 表示事件名称；
    # data 表示本次事件携带的 JSON；
    # 最后的两个换行表示一个事件结束。
    return f"event: {event_name}\ndata: {json_data}\n\n"


@router.post(
    "/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    dependencies=[Depends(require_permission(Permission.KNOWLEDGE_CHAT_USE))],
    summary="指定会话中发送消息",
)
async def create_message(
    current_user: CurrentUser,
    service: KnowledgeChatServiceDep,
    session_id: int,
    request_id: RequestId,
    payload: KnowledgeChatMessageCreateDTO,
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        """把 Service 业务事件持续转换成浏览器可读取的 SSE 文本。"""

        try:
            # Service 每完成一个阶段，就产生一个事件类型和对应的 VO。
            async for event_type, event_data in service.stream_message(
                current_user=current_user,
                session_id=session_id,
                request_id=request_id,
                payload=payload,
            ):
                # 把业务事件转换成 SSE 文本并立即发送，而不是等全部完成。
                yield format_sse_event(
                    event_type=event_type,
                    data=event_data,
                )
        except Exception as exc:
            # StreamingResponse 一旦开始发送，HTTP 状态码和响应头就已经确定，
            # 无法再切换成项目统一的 ApiResult 错误 JSON。
            #
            # 这里主要兜底 Service 内层 try 之前发生的异常，例如：
            # - 会话不存在或不属于当前用户；
            # - 会话已经归档；
            # - 知识库不存在、无权限或已停用。
            # 生成阶段的异常通常已由 Service 更新 FAILED 消息并发送 ERROR。
            yield format_sse_event(
                event_type=KnowledgeChatStreamEventType.ERROR,
                data=KnowledgeChatStreamErrorVO(
                    message=describe_exception(exc),
                    # 早期校验尚未创建 ASSISTANT/PENDING，所以没有消息可返回。
                    assistant_message=None,
                ),
            )

    return StreamingResponse(
        content=event_stream(),
        media_type="text/event-stream",
        headers={
            # SSE 不能被浏览器或代理缓存。
            "Cache-Control": "no-cache",
            # 保持 HTTP 连接，允许后端继续发送事件。
            "Connection": "keep-alive",
            # 禁止 Nginx 缓冲，否则可能最后一次性显示所有文字。
            "X-Accel-Buffering": "no",
        },
    )
