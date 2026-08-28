from sqlalchemy.exc import IntegrityError

from app.core.constants import AIModelTaskType
from app.exceptions import BadRequestException, ConflictException, ExternalServiceException, NotFoundException
from app.models import AIModel, User
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.ai_provider_repository import AIProviderRepository
from app.schemas.dto.ai_model import AIConnectionTestDTO, AIModelCreateDTO, AIModelUpdateDTO
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO
from app.schemas.vo.ai_model import AIConnectionResultVO, AIModelVO
from app.utils.ai_client_util import generate_embedding, generate_text, rerank_documents


class AIModelService:
    def __init__(self, repository: AIModelRepository, provider_repository: AIProviderRepository) -> None:
        self.repository = repository
        self.provider_repository = provider_repository

    @staticmethod
    def _model_read(model: AIModel) -> AIModelVO:
        return AIModelVO.model_validate(
            {
                **model.__dict__,
                "provider_name": model.provider.name if model.provider else "",
            }
        )

    @staticmethod
    def _validate_token_limits(
            context_window_tokens: int,
            max_output_tokens: int,
    ) -> None:
        if max_output_tokens >= context_window_tokens:
            raise BadRequestException(
                "最大输出 Token 必须小于模型上下文窗口"
            )

    async def list_model(self):
        return [self._model_read(item) for item in await self.repository.list_models()]

    async def create_model(self, payload: AIModelCreateDTO) -> AIModelVO:
        self._validate_token_limits(payload.context_window_tokens, payload.max_output_tokens)
        if await self.provider_repository.get_provider(payload.provider_id) is None:
            raise NotFoundException("AI 服务商不存在")
        if payload.is_default:
            await self.repository.clear_default_models()
        model = AIModel(**payload.model_dump())
        self.repository.add(model)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("该服务商下的模型标识已经存在") from e
        loaded = await self.repository.get_model(model.id)
        if loaded is None:
            raise NotFoundException("AI 模型不存在")
        return self._model_read(loaded)

    async def update_model(self, model_pk: int, payload: AIModelUpdateDTO) -> AIModelVO:
        model = await self.repository.get_model(model_pk, with_provider=False)
        if model is None:
            raise NotFoundException("AI 模型不存在")
        changes = payload.model_dump(exclude_unset=True)
        context_window_tokens = changes.get(
            "context_window_tokens",
            model.context_window_tokens,
        )
        max_output_tokens = changes.get(
            "max_output_tokens",
            model.max_output_tokens,
        )
        self._validate_token_limits(context_window_tokens, max_output_tokens)
        if changes.get("is_default"):
            await self.repository.clear_default_models()
        for key, value in changes.items():
            setattr(model, key, value)
        await self.repository.commit()
        loaded = await self.repository.get_model(model.id)
        if loaded is None:
            raise NotFoundException("AI 模型不存在")
        return self._model_read(loaded)

    async def delete_model(self, model_pk: int):
        model = await self.repository.get_model(model_pk, with_provider=False)
        if model is None:
            raise NotFoundException("AI 模型不存在")
        await self.repository.delete(model)
        await self.repository.commit()

    async def test_connection(
        self,
        payload: AIConnectionTestDTO,
        current_user: User,
        request_id: str,
    ) -> AIConnectionResultVO:
        model = await self.repository.get_model(payload.model_id)
        if model is None or not model.enabled or not model.provider.enabled:
            raise BadRequestException("模型不存在或已停用")
        usage_context = AIUsageContextDTO(
            request_id=request_id,
            user_id=current_user.id,
        )
        try:
            if AIModelTaskType.EMBEDDING.value in model.task_types:
                result = await generate_embedding(
                    self.repository,
                    model.provider,
                    model,
                    payload.prompt,
                    "connection_test",
                    usage_context
                )
                return AIConnectionResultVO(
                    success=True,
                    content=f"Embedding 生成成功，向量维度：{len(result.vector)}",
                    latency_ms=result.latency_ms,
                )
            if AIModelTaskType.RERANK.value in model.task_types:
                result = await rerank_documents(
                    repository=self.repository,
                    provider=model.provider,
                    model=model,
                    query=payload.prompt,
                    documents=[
                        f"这是一段与用户问题相关的测试内容：{payload.prompt}",
                        "量子计算是一种使用量子力学原理进行计算的技术。",
                        "测试平台支持项目、模块和测试环境管理。",
                    ],
                    top_n=3,
                    task_type="connection_test",
                    usage_context=usage_context
                )
                score_text = "，".join(
                    (
                        f"下标{item.index}="
                        f"{item.relevance_score:.4f}"
                    )
                    for item in result.results
                )
                return AIConnectionResultVO(
                    success=True,
                    content=f"Rerank调用成功，排序分数：{score_text}",
                    latency_ms=result.latency_ms,
                )
            result = await generate_text(
                self.repository,
                model.provider,
                model,
                "你是连接测试助手，请简短回答。",
                payload.prompt,
                "connection_test",
                usage_context
            )
        except Exception as e:
            raise ExternalServiceException(f"AI 连接失败：{e}") from e
        return AIConnectionResultVO(success=True, content=result.content, latency_ms=result.latency_ms)
