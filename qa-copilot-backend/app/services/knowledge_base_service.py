from sqlalchemy.exc import IntegrityError

from app.core.constants import AIModelTaskType, ProjectStatus
from app.exceptions import BadRequestException, ConflictException, NotFoundException
from app.models import KnowledgeBase, User
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.knowledge_bases import KnowledgeBaseCreateDTO, KnowledgeBaseUpdateDTO
from app.schemas.vo.knowledge_bases import KnowledgeBaseVO, KnowledgeModelOptionVO


class KnowledgeBaseService:
    def __init__(
        self,
        repository: KnowledgeBaseRepository,
        project_repository: TestProjectsRepository,
        model_repository: AIModelRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.model_repository = model_repository

    @staticmethod
    def _knowledge_base_read(knowledge_base: KnowledgeBase) -> KnowledgeBaseVO:
        """把数据库实体转换成前端需要的知识库 VO。"""

        return KnowledgeBaseVO(
            id=knowledge_base.id,
            project_id=knowledge_base.project_id,
            name=knowledge_base.name,
            description=knowledge_base.description,
            visibility=knowledge_base.visibility,
            embedding_model_id=knowledge_base.embedding_model_id,
            embedding_model_name=knowledge_base.embedding_model.name,
            rerank_model_id=knowledge_base.rerank_model_id,
            rerank_model_name=(
                knowledge_base.rerank_model.name
                if knowledge_base.rerank_model
                else None
            ),
            document_count=knowledge_base.document_count or 0,
            chunk_count=knowledge_base.chunk_count or 0,
            enabled=knowledge_base.enabled,
            created_by=knowledge_base.created_by,
            created_by_name=(
                knowledge_base.creator.display_name
                if knowledge_base.creator
                else None
            ),
            created_at=knowledge_base.created_at,
            updated_at=knowledge_base.updated_at,
        )

    async def list_model_options(
        self,
        task_type: AIModelTaskType,
    ) -> list[KnowledgeModelOptionVO]:
        # 1. 调用 model_repository.list_models() 查询平台已经配置的全部 AI 模型。
        ai_models = await self.model_repository.list_models()
        # 2. 遍历模型，只保留同时满足以下三个条件的记录：
        #    - 模型自身 enabled 为 True；
        #    - 模型所属 provider.enabled 为 True；
        #    - task_type.value 存在于模型的 task_types 列表中。
        knowledge_models: list[KnowledgeModelOptionVO] = []
        for ai_model in ai_models:
        # 3. 把每个符合条件的 AIModel 转换成 KnowledgeModelOptionVO：
        #    - id 使用 model.id；
        #    - name 使用 model.name；
        #    - model_id 使用 model.model_id；
        #    - provider_name 使用 model.provider.name。
            if not ai_model.enabled or not ai_model.provider.enabled or task_type.value not in ai_model.task_types:
                continue
            knowledge_model = KnowledgeModelOptionVO(
                id=ai_model.id,
                name=ai_model.name,
                model_id=ai_model.model_id,
                provider_name=ai_model.provider.name,
            )
            knowledge_models.append(knowledge_model)

        # 4. 返回转换完成的选项列表。没有符合条件的模型时返回空列表。
        return knowledge_models

    async def list_knowledge_bases(
            self,
            project_id: int,
            current_user: User,
            keyword: str,
            enabled: bool | None,
            current: int,
            size: int,
    ) -> tuple[list[KnowledgeBaseVO], int]:
        project = await self.project_repository.get_accessible_project(project_id,current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        knowledge_bases,total  = await self.repository.list_knowledge_bases(
            project_id,
            current_user,
            keyword,
            enabled,
            current,
            size,)
        records = [self._knowledge_base_read(knowledge_base) for knowledge_base in knowledge_bases]
        return records,total

    async def create_knowledge_base(
            self,
            project_id: int,
            current_user: User,
            payload: KnowledgeBaseCreateDTO,
    ) -> KnowledgeBaseVO:
        project = await self.project_repository.get_accessible_project(project_id,current_user)
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestException("已归档项目不能创建知识库")
        ai_model = await self.model_repository.get_model(model_pk=payload.embedding_model_id)
        if ai_model is None:
            raise NotFoundException("Embedding 模型不存在")
        if not ai_model.enabled or not ai_model.provider.enabled:
            raise BadRequestException("Embedding 模型不可用")
        if AIModelTaskType.EMBEDDING.value not in ai_model.task_types:
            raise BadRequestException("所选模型不支持 Embedding 任务")
        rerank_model  = None
        if payload.rerank_model_id is not None:
            rerank_model = await self.model_repository.get_model(model_pk=payload.rerank_model_id)
            if rerank_model is None:
                raise NotFoundException("Rerank 模型不存在")
            if not rerank_model.enabled or not rerank_model.provider.enabled:
                raise BadRequestException("Rerank 模型不可用")
            if AIModelTaskType.RERANK.value not in rerank_model.task_types:
                raise BadRequestException("所选模型不支持 Rerank 任务")
        existing = await self.repository.get_by_name(project_id,payload.name)
        if existing is not None:
            raise ConflictException("当前项目已存在同名知识库")
        knowledge_base = KnowledgeBase(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility.value,
            embedding_model_id=ai_model.id,
            rerank_model_id= rerank_model.id if rerank_model is not None else None,
            enabled=payload.enabled,
            created_by=current_user.id,
            project=project,
            embedding_model=ai_model,
            rerank_model=rerank_model,
            creator=current_user
        )
        self.repository.add(knowledge_base)
        try:
            await self.repository.commit()
        except IntegrityError as e:
            await self.repository.rollback()
            raise ConflictException("当前项目已存在同名知识库") from e
        return self._knowledge_base_read(knowledge_base)

    async def update_knowledge_base(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
            payload: KnowledgeBaseUpdateDTO,
    ) -> KnowledgeBaseVO:
        # 先确认当前用户属于该项目，避免外部用户仅凭项目 ID 访问项目级知识库。
        project = await self.project_repository.get_accessible_project(
            project_id,
            current_user,
        )
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能编辑知识库")

        # 再按知识库可见范围查询目标，防止修改无权访问的 PRIVATE/MANAGERS 数据。
        knowledge_base = await self.repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user,
        )
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权操作")

        fields_set = payload.model_fields_set

        # 名称只有在前端实际传入时才更新，并排除当前记录检查同项目重名。
        if (
            "name" in fields_set
            and payload.name is not None
        ):
            existing = await self.repository.get_by_name(
                project_id,
                payload.name,
                exclude_id=knowledge_base_id,
            )
            if existing is not None:
                raise ConflictException("当前项目已存在同名知识库")
            knowledge_base.name = payload.name

        # 这三个字段不需要额外查询，按前端实际传入情况直接更新。
        if "description" in fields_set and payload.description is not None:
            knowledge_base.description = payload.description
        if "visibility" in fields_set and payload.visibility is not None:
            knowledge_base.visibility = payload.visibility.value
        if "enabled" in fields_set and payload.enabled is not None:
            knowledge_base.enabled = payload.enabled

        # Embedding 模型是必填配置；更新时必须验证模型及其服务商可用，
        # 同时更新外键和关系对象，保证返回 VO 中的模型名称也是最新值。
        if (
            "embedding_model_id" in fields_set
            and payload.embedding_model_id is not None
        ):
            embedding_model = await self.model_repository.get_model(
                model_pk=payload.embedding_model_id
            )
            if embedding_model is None:
                raise NotFoundException("Embedding 模型不存在")
            if (
                not embedding_model.enabled
                or not embedding_model.provider.enabled
            ):
                raise BadRequestException("Embedding 模型不可用")
            if (
                AIModelTaskType.EMBEDDING.value
                not in embedding_model.task_types
            ):
                raise BadRequestException("所选模型不支持 Embedding 任务")
            knowledge_base.embedding_model_id = embedding_model.id
            knowledge_base.embedding_model = embedding_model

        # Rerank 模型是可选配置。字段未传表示保持原值；显式传 null 表示清空；
        # 传入模型 ID 时，则执行与创建知识库相同的可用性和任务类型校验。
        if "rerank_model_id" in fields_set:
            if payload.rerank_model_id is None:
                knowledge_base.rerank_model_id = None
                knowledge_base.rerank_model = None
            else:
                rerank_model = await self.model_repository.get_model(
                    model_pk=payload.rerank_model_id
                )
                if rerank_model is None:
                    raise NotFoundException("Rerank 模型不存在")
                if (
                    not rerank_model.enabled
                    or not rerank_model.provider.enabled
                ):
                    raise BadRequestException("Rerank 模型不可用")
                if (
                    AIModelTaskType.RERANK.value
                    not in rerank_model.task_types
                ):
                    raise BadRequestException("所选模型不支持 Rerank 任务")
                knowledge_base.rerank_model_id = rerank_model.id
                knowledge_base.rerank_model = rerank_model

        # 数据库唯一约束负责兜底处理并发重名；失败后必须回滚 Session。
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("当前项目已存在同名知识库") from exc

        return self._knowledge_base_read(knowledge_base)

    async def delete_knowledge_base(
            self,
            project_id: int,
            knowledge_base_id: int,
            current_user: User,
    ) -> None:
        # 1. 根据 project_id 和 current_user 查询当前用户可访问的项目。
        #    不能只根据 project_id 直接查项目，否则非项目成员可能通过手动修改
        #    URL 中的项目 ID，尝试删除其他项目的知识库。
        project = await self.project_repository.get_accessible_project(project_id,current_user)
        # 2. 如果项目不存在，或者当前用户不是该项目负责人/成员，
        #    抛出 NotFoundException("项目不存在或无权操作")。
        #    对无权访问的情况同样返回“不存在”，避免向外部用户泄露项目是否存在。
        if project is None:
            raise NotFoundException("项目不存在或无权操作")
        # 3. 判断项目状态是否为 ProjectStatus.ARCHIVED。
        #    已归档项目属于只读历史数据，不允许继续删除知识库；如果已归档，
        #    抛出 BadRequestException("已归档项目不能删除知识库")。
        if project.status == ProjectStatus.ARCHIVED.value:
            raise BadRequestException("已归档项目不能删除知识库")
        # 4. 调用 repository.get_accessible_knowledge_base() 查询准备删除的知识库。
        #    查询时必须同时传入 project_id、knowledge_base_id 和 current_user：
        #    - project_id 防止通过知识库 ID 跨项目操作；
        #    - current_user 用于继续应用 PROJECT、MANAGERS、PRIVATE 可见范围。
        knowledge_base = await self.repository.get_accessible_knowledge_base(
            project_id,
            knowledge_base_id,
            current_user,
        )
        # 5. 如果知识库不存在，或当前用户不能访问该知识库，
        #    抛出 NotFoundException("知识库不存在或无权操作")。
        if knowledge_base is None:
            raise NotFoundException("知识库不存在或无权操作")
        # 6. 调用 await repository.delete(knowledge_base)，把实体标记为待删除。
        #    delete() 此时还没有永久写入数据库，真正执行和确认删除要等到 commit()。
        await self.repository.delete(knowledge_base)
        # 7. 在 try 中调用 await repository.commit() 提交删除事务。
        #    如果数据库因为关联数据或外键约束抛出 IntegrityError：
        #    - 先调用 await repository.rollback() 恢复 Session，使它可以继续使用；
        #    - 再抛出 ConflictException("知识库仍有关联数据，无法删除")，
        #      并使用 `from exc` 保留原始数据库异常，方便后台日志排查。
        try:
            await self.repository.commit()
        except IntegrityError as exc:
            await self.repository.rollback()
            raise ConflictException("知识库仍有关联数据，无法删除") from exc
        # 8. 删除成功后不需要返回业务数据，方法自然结束并返回 None。
