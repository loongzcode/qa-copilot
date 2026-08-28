from sqlalchemy.exc import IntegrityError

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.exceptions import ConflictException, NotFoundException
from app.models import AIProvider
from app.repositories.ai_provider_repository import AIProviderRepository
from app.schemas.dto.ai_provider import AIProviderCreateDTO, AIProviderUpdateDTO
from app.schemas.vo.ai_provider import AIProviderVO


class AiProviderService:
    def __init__(self,repository:AIProviderRepository) -> None:
        self.repository = repository
    @staticmethod
    def _provider_read(provider: AIProvider) -> AIProviderVO:
        raw_key = decrypt_secret(provider.encrypted_api_key) if provider.encrypted_api_key else ""
        return AIProviderVO.model_validate(
            {**provider.__dict__, "api_key_masked": mask_secret(raw_key)}
        )

    async def list_providers(self):
        return [self._provider_read(item) for item in await self.repository.list_providers()]

    async def create_provider(self, payload: AIProviderCreateDTO) -> AIProviderVO:
        provider = AIProvider(**payload.model_dump(exclude={"api_key"}),
                              encrypted_api_key=encrypt_secret(payload.api_key))
        self.repository.add(provider)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("AI 服务商名称已经存在") from e
        return self._provider_read(provider)

    async def update_provider(self, provider_id: int, payload: AIProviderUpdateDTO) -> AIProviderVO:
        provider = await self.repository.get_provider(provider_id)
        if provider is None:
            raise NotFoundException("AI 服务商不存在")
        changes = payload.model_dump(exclude_unset=True)
        api_key = changes.pop("api_key", None)
        for key, value in changes.items():
            setattr(provider, key, value)
        if api_key:
            provider.encrypted_api_key = encrypt_secret(api_key)
        await self.repository.commit()
        return self._provider_read(provider)

    async def delete_provider(self, provider_id):
        provider = await self.repository.get_provider(provider_id)
        if provider is None:
            raise NotFoundException("AI 服务商不存在")
        await self.repository.delete(provider)
        await self.repository.commit()
