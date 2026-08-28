"""AI 需求拆解任务的提交、状态查询和失败恢复业务层。"""
from uuid import uuid4

from app.core.constants import (
    KnowledgeDocumentParseStatus,
    RequirementExtractionStage,
    RequirementExtractionTaskStatus,
    RequirementStatus,
)
from app.exceptions import (
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    InternalServerException,
    NotFoundException,
)
from app.mappers.requirements import requirement_extraction_task_to_vo
from app.models import Requirement, RequirementExtractionTask
from app.models.mixins import utc_now
from app.models.user import User
from app.repositories.requirement_extraction_tasks_repository import (
    RequirementExtractionTasksRepository,
)
from app.repositories.requirements_repository import RequirementsRepository
from app.repositories.test_projects_repository import TestProjectsRepository
from app.schemas.dto.requirements import RequirementExtractionSubmitDTO
from app.schemas.vo.requirements import RequirementExtractionTaskVO
from app.workers.requirement_extraction_dispatcher import enqueue_requirement_extraction


class RequirementExtractionService:
    """组织 API 请求、任务记录和 Celery 投递，不直接执行耗时 AI 工作流。"""

    def __init__(
            self,
            requirement_extraction_tasks_repository: RequirementExtractionTasksRepository,
            requirements_repository: RequirementsRepository,
            test_project_repository: TestProjectsRepository,
    ) -> None:
        self.requirement_extraction_tasks_repository = (
            requirement_extraction_tasks_repository
        )
        self.requirements_repository = requirements_repository
        self.test_project_repository = test_project_repository

    async def _get_accessible_requirement(
            self,
            project_id: int,
            requirement_id: int,
            current_user: User,
            *,
            lock: bool = False,
    ) -> Requirement:
        """统一校验项目权限并取得项目内需求。

        为什么需要这个私有方法：提交、查询最新任务和查询指定任务都不能仅凭
        requirement_id 访问数据。三个公开方法都必须先校验项目访问权和需求归属，
        集中处理可以避免其中某个接口遗漏数据权限。

        实现顺序：
        1. 用 test_project_repository.get_accessible_project() 查询当前用户可访问项目；
        2. 项目不存在时抛出 NotFoundException；
        3. 用 requirements_repository.get_requirement_detail() 查询需求，并传入 lock；
        4. 需求不存在时抛出 NotFoundException；
        5. 返回 Requirement 实体。
        """
        test_project = await self.test_project_repository.get_accessible_project(
            project_id, current_user
        )
        if test_project is None:
            raise NotFoundException("项目不存在或无权访问")
        requirement = await self.requirements_repository.get_requirement_detail(
            project_id, requirement_id, lock=lock
        )
        if requirement is None:
            raise NotFoundException("需求不存在或无权访问")
        return requirement

    async def submit_extraction(
            self,
            project_id: int,
            requirement_id: int,
            payload: RequirementExtractionSubmitDTO,
            current_user: User,
    ) -> RequirementExtractionTaskVO:
        """保存可恢复的任务记录，然后投递 Celery 需求拆解任务。

        完整业务流程：
        1. 调用 _get_accessible_requirement(..., lock=True) 锁住需求主记录；
        2. ARCHIVED 需求不允许再次拆解；
        3. 查询该需求是否已有 PENDING/RUNNING 任务，有则抛 ConflictException；
        4. 确定拆解来源：有关联文档时要求文档已经 READY；没有文档时要求
           requirement.summary 去除空格后不为空，否则没有可供 AI 拆解的正文；
        5. 使用 uuid4() 预先生成 celery_task_id；
        6. 创建 RequirementExtractionTask，input_snapshot 保存需求版本、文档信息、
           来源类型以及 replace_unconfirmed_ai_items，状态设为 PENDING/QUEUED；
        7. 把需求状态改为 EXTRACTING，同时更新时间；
        8. add() 任务并 commit()，先在数据库建立可恢复的任务记录；
        9. commit 成功后调用 enqueue_requirement_extraction() 投递 Celery；
        10. 投递失败时，把任务和需求都改为 FAILED、保存脱敏错误并再次 commit，
            然后抛 ExternalServiceException；
        11. 投递成功后重新查询任务，转换为 VO 返回。

        为什么先提交数据库再发 Celery：Worker 可能在消息发出后立刻开始执行。
        如果此时任务记录尚未提交，Worker 会查不到任务。先保存相当于先创建工单，
        再通知工人领取。
        """
        requirement = await self._get_accessible_requirement(project_id, requirement_id, current_user, lock=True)
        if requirement.status == RequirementStatus.ARCHIVED.value:
            raise BadRequestException("已归档需求不允许再次拆解")
        active_task = (
            await self.requirement_extraction_tasks_repository.get_active_task(
                requirement_id
            )
        )
        if active_task is not None:
            raise ConflictException("该需求已有排队中或正在执行的拆解任务")
        celery_task_id = str(uuid4())
        document = requirement.document
        if document is None:
            summary = requirement.summary.strip()
            if not summary:
                raise BadRequestException(
                    "需求未关联原始文档，也没有可供拆解的需求摘要"
                )
            source_type = "SUMMARY"
            document_id = None
            document_version = None
        else:
            if (
                    document.parse_status
                    != KnowledgeDocumentParseStatus.READY.value
            ):
                raise BadRequestException(
                    "关联的原始需求文档尚未完成解析和索引"
                )
            source_type = "DOCUMENT"
            document_id = document.id
            document_version = document.version
        requirement_task = RequirementExtractionTask(
            project_id=project_id,
            requirement_id=requirement_id,
            celery_task_id=celery_task_id,
            status=RequirementExtractionTaskStatus.PENDING.value,
            progress=0,
            current_stage=RequirementExtractionStage.QUEUED.value,
            input_snapshot={
                "requirement_version": requirement.version,
                "document_id": document_id,
                "document_version": document_version,
                "source_type": source_type,
                "replace_unconfirmed_ai_items":
                    payload.replace_unconfirmed_ai_items,
                "summary": requirement.summary,
            },
            output_snapshot={},
            requested_by=current_user.id
        )
        requirement.status = RequirementStatus.EXTRACTING.value
        requirement.updated_at = utc_now()
        self.requirement_extraction_tasks_repository.add(requirement_task)
        await self.requirement_extraction_tasks_repository.commit()
        try:
            await enqueue_requirement_extraction(
                requirement_task.id,
                celery_task_id,
            )
        except Exception as exc:
            failed_at = utc_now()
            requirement_task.status = RequirementExtractionTaskStatus.FAILED.value
            requirement_task.error_message = (
                f"Celery 任务投递失败：{type(exc).__name__}"
            )
            requirement_task.finished_at = failed_at
            requirement.status = RequirementStatus.FAILED.value
            requirement.updated_at = failed_at
            await self.requirement_extraction_tasks_repository.commit()
            raise ExternalServiceException("需求拆解任务投递失败，请检查 Redis 和 Celery Worker") from exc
        saved_task = (
            await self.requirement_extraction_tasks_repository.get_task(
                project_id,
                requirement_id,
                requirement_task.id,
            )
        )
        if saved_task is None:
            raise InternalServerException("需求拆解任务创建后读取失败")
        return requirement_extraction_task_to_vo(saved_task)

    async def get_latest_task(
            self,
            project_id: int,
            requirement_id: int,
            current_user: User,
    ) -> RequirementExtractionTaskVO | None:
        """查询需求最近一次拆解任务，供页面刷新后恢复进度。

        1. 先调用 _get_accessible_requirement() 完成数据权限和需求归属校验；
        2. Repository 按 created_at、id 倒序查询第一条任务；
        3. 没有历史任务时返回 None；
        4. 有任务时通过 requirement_extraction_task_to_vo() 转换后返回。
        """
        await self._get_accessible_requirement(project_id, requirement_id, current_user)
        latest_task = await self.requirement_extraction_tasks_repository.get_latest_task(
            project_id,
            requirement_id,
        )
        if latest_task is None:
            return None

        return requirement_extraction_task_to_vo(latest_task)

    async def get_task(
            self,
            project_id: int,
            requirement_id: int,
            task_id: int,
            current_user: User,
    ) -> RequirementExtractionTaskVO:
        """查询一条准确任务，供前端使用 task_id 轮询执行进度。

        1. 先调用 _get_accessible_requirement() 校验项目和需求；
        2. Repository 必须同时使用 project_id、requirement_id、task_id 查询，避免
           用户拿其他项目的 task_id 越权读取任务快照；
        3. 任务不存在时抛出 NotFoundException；
        4. 转换成 RequirementExtractionTaskVO 返回。
        """
        await self._get_accessible_requirement(project_id, requirement_id, current_user)
        task = await self.requirement_extraction_tasks_repository.get_task(
            project_id,
            requirement_id,
            task_id,
        )
        if task is None:
            raise NotFoundException("任务不存在")

        return requirement_extraction_task_to_vo(task)
