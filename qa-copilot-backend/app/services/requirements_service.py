from app.core.constants import RequirementStatus
from app.exceptions import BadRequestException, InternalServerException, NotFoundException
from app.mappers.requirements import requirement_detail_to_vo, requirement_to_vo
from app.models import KnowledgeDocument, Requirement, User
from app.models.mixins import utc_now
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_modules_repository import TestModulesRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.requirements import RequirementCreateDTO, RequirementUpdateDTO
from app.schemas.vo.requirements import (
    RequirementDetailVO,
    RequirementDocumentOptionVO,
    RequirementFormOptionsVO,
    RequirementKnowledgeBaseOptionVO,
    RequirementModuleOptionVO,
    RequirementVO,
)


class RequirementsService:
    """编排需求管理、数据权限和后续 AI 拆解流程。"""

    def __init__(
            self,
            repository: RequirementsRepository,
            test_project_repository: TestProjectsRepository,
            test_module_repository: TestModulesRepository,
            knowledge_base_repository: KnowledgeBaseRepository,
            knowledge_document_repository: KnowledgeDocumentRepository,
    ) -> None:
        # 当前模块自己的需求数据访问。
        self.repository = repository
        # 校验项目是否存在以及当前用户是否属于该项目。
        self.test_project_repository = test_project_repository
        # 校验需求关联的功能模块是否属于当前项目。
        self.test_module_repository = test_module_repository
        # 查询当前用户可访问的知识库，供“直接上传需求来源文档”选择保存位置。
        self.knowledge_base_repository = knowledge_base_repository
        # 校验关联的需求来源文档是否存在、可访问且属于当前项目。
        self.knowledge_document_repository = knowledge_document_repository

    async def _get_accessible_requirement_document(
            self,
            project_id: int,
            document_id: int,
            current_user: User,
    ) -> KnowledgeDocument | None:
        """查询当前用户真正有权关联的项目需求来源文档。

        功能：先按项目和文档类型定位需求文档，再校验其所属知识库的可见范围。
        作用：创建和编辑需求共用这一入口，防止用户通过猜测 document_id 关联
        PRIVATE 或 MANAGERS 范围内自己无权访问的文档。
        为什么用它：项目成员权限和知识库可见性是两层不同限制，只有项目权限
        不足以证明能读取其中每个知识库；集中校验可避免两个写接口规则不一致。
        """

        document = await self.knowledge_document_repository.get_project_requirement_document(
            project_id,
            document_id,
        )
        if document is None:
            return None
        knowledge_base = await self.knowledge_base_repository.get_accessible_knowledge_base(
            project_id,
            document.knowledge_base_id,
            current_user,
        )
        return document if knowledge_base is not None else None

    async def list_requirements(
            self,
            project_id: int,
            current_user: User,
            keyword: str,
            status: RequirementStatus | None,
            current: int,
            size: int,
    ):
        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        keyword = keyword.strip()
        records, total = await self.repository.list_requirements(project_id, keyword, status, current, size)
        requirement_list = [requirement_to_vo(requirement) for requirement in records]
        return requirement_list, total

    async def get_form_options(
            self,
            project_id: int,
            current_user: User,
    ) -> RequirementFormOptionsVO:
        """返回需求表单需要的模块、知识库和已有来源文档选项。

        完整业务流程：
        1. 校验当前用户能够访问该项目；
        2. 查询该项目的全部功能模块；
        3. 查询当前用户可访问的已启用知识库，供直接上传时选择保存位置；
        4. 查询该项目中已解析完成、可直接作为需求来源的文档；
        5. 把实体转换成轻量下拉选项 VO 后返回。
        """
        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        module_list = await self.test_module_repository.list_modules(project.id)
        knowledge_bases, _ = await self.knowledge_base_repository.list_knowledge_bases(
            project_id=project_id,
            current_user=current_user,
            keyword="",
            enabled=True,
            current=1,
            size=1000,
        )
        requirement_documents = await self.knowledge_document_repository.list_project_requirement_documents(project_id)
        accessible_knowledge_base_ids = {
            knowledge_base.id for knowledge_base in knowledge_bases
        }
        requirement_documents = [
            document
            for document in requirement_documents
            if document.knowledge_base_id in accessible_knowledge_base_ids
        ]
        requirement_modules = [RequirementModuleOptionVO(id=model.id, name=model.name) for model in module_list]
        requirement_document_options = [
            RequirementDocumentOptionVO(
                id=requirement_document.id,
                title=requirement_document.title,
                version=requirement_document.version)
            for requirement_document in requirement_documents
        ]

        knowledge_base_options = [
            RequirementKnowledgeBaseOptionVO(id=knowledge_base.id, name=knowledge_base.name)
            for knowledge_base in knowledge_bases
        ]

        return RequirementFormOptionsVO(
            modules=requirement_modules,
            knowledge_bases=knowledge_base_options,
            documents=requirement_document_options,
        )

    async def create_requirement(
            self,
            project_id: int,
            payload: RequirementCreateDTO,
            current_user: User,
    ) -> RequirementVO:
        """在当前用户可访问的项目中创建需求。

        完整业务流程：
        1. 校验项目访问权限；
        2. 校验可选 module_id 确实属于当前项目；
        3. 校验可选 document_id 来自当前项目；未关联文档时要求填写需求摘要；
        4. 创建 DRAFT 状态的 Requirement 实体并记录创建人；
        5. 提交事务后重新查询关联对象和统计字段；
        6. 转换成 RequirementVO 返回。
        """
        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        if payload.module_id is not None:
            module = await self.test_module_repository.get_module(project_id,payload.module_id)
            if module is None:
                raise NotFoundException("项目模块不存在")
        if payload.document_id is not None:
            document = await self._get_accessible_requirement_document(
                project_id,
                payload.document_id,
                current_user,
            )
            if document is None:
                raise NotFoundException("需求来源文档不存在或无权访问")
        elif not payload.summary:
            raise BadRequestException("手工录入需求时必须填写需求摘要")
        requirement = Requirement(
            project_id=project_id,
            created_by=current_user.id,
            status=RequirementStatus.DRAFT.value,
            module_id=payload.module_id,
            document_id=payload.document_id,
            title=payload.title,
            version=payload.version,
            source_url=payload.source_url,
            summary=payload.summary,
            requirement_metadata=payload.metadata,
        )
        self.repository.add(requirement)
        await self.repository.commit()
        requirement_detail = await self.repository.get_requirement_detail(project_id, requirement.id)
        if requirement_detail is None:
            raise InternalServerException("需求创建后读取失败")
        return requirement_to_vo(requirement_detail)



    async def get_requirement_detail(
            self,
            project_id: int,
            requirement_id: int,
            current_user: User,
    ) -> RequirementDetailVO:
        """查询需求主记录及其全部原子需求点。

        完整业务流程：
        1. 校验项目访问权限；
        2. 按 project_id 和 requirement_id 查询未删除需求；
        3. 找不到时统一返回“需求不存在”；
        4. 将需求主记录和有序需求点转换成详情 VO。
        """
        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        requirement = await self.repository.get_requirement_detail(
            project_id,
            requirement_id,
        )
        if requirement is None:
            raise NotFoundException("需求不存在")

        return requirement_detail_to_vo(requirement)

    async def update_requirement(
            self,
            project_id: int,
            requirement_id: int,
            payload: RequirementUpdateDTO,
            current_user: User,
    ) -> RequirementVO:
        """更新需求主记录中前端明确传入的字段。

        完整业务流程：
        1. 校验项目权限并查询目标需求；
        2. 只在 payload 传入 module_id/document_id 时重新校验关联；
        3. 使用 exclude_unset=True 取得真正需要修改的字段；
        4. 将 DTO 的 metadata 映射到实体 requirement_metadata；
        5. 提交后重新查询并返回最新 RequirementVO。
        """

        project = await self.test_project_repository.get_accessible_project(
            project_id,
            current_user
        )
        if project is None:
            raise NotFoundException("项目不存在或无权访问")
        requirement_detail = await self.repository.get_requirement_detail(project_id,requirement_id)
        if requirement_detail is None:
            raise NotFoundException("需求不存在")
        changes = payload.model_dump(exclude_unset=True)
        if "module_id" in changes and changes["module_id"] is not None:
            module = await self.test_module_repository.get_module(project_id,changes.get("module_id"))
            if module is None:
                raise NotFoundException("项目模块不存在")
        if "document_id" in changes and changes["document_id"] is not None:
            document = await self._get_accessible_requirement_document(
                project_id,
                changes["document_id"],
                current_user,
            )
            if document is None:
                raise NotFoundException("需求来源文档不存在或无权访问")
        final_document_id = changes.get("document_id", requirement_detail.document_id)
        final_summary = changes.get("summary", requirement_detail.summary)
        if final_document_id is None and not final_summary:
            raise BadRequestException("手工录入需求时必须填写需求摘要")
        if "metadata" in changes:
            requirement_detail.requirement_metadata = changes.pop("metadata")
        for key,value in changes.items():
            setattr(requirement_detail,key,value)
        await self.repository.commit()
        requirement_detail = await self.repository.get_requirement_detail(project_id, requirement_id)
        if requirement_detail is None:
            raise InternalServerException("需求更新后读取失败")
        return requirement_to_vo(requirement_detail)

    async def delete_requirement(
            self,
            project_id: int,
            requirement_id: int,
            current_user: User,
    ) -> None:
        """软删除当前项目中的需求，保留历史数据和审计关系。

        完整业务流程：
        1. 校验项目访问权限；
        2. 查询当前项目中未删除的目标需求；
        3. 将 deleted_at 设置为当前 UTC 时间；
        4. 提交事务，不物理删除需求点和后续生成记录。
        """
        test_project = await self.test_project_repository.get_accessible_project(project_id,current_user)
        if test_project is None:
            raise NotFoundException("项目不存在或无权访问")
        requirement = await self.repository.get_requirement_detail(project_id,requirement_id)
        if requirement is None:
            raise NotFoundException("需求不存在")
        requirement.deleted_at = utc_now()
        await self.repository.commit()
