from sqlalchemy import select

from app.models import AIProvider
from app.repositories.base_repository import BaseRepository


class AIProviderRepository(BaseRepository):
    async def list_providers(self):
        return list((await self.session.scalars(select(AIProvider).order_by(AIProvider.id))).all())

    async def get_provider(self, provider_id):
        return await self.session.scalar(select(AIProvider).where(AIProvider.id == provider_id))
