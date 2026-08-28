"""Celery 需求拆解任务的业务执行服务。

本模块负责把已领取的数据库任务依次推进到读取需求、运行 LangGraph 和记录失败
状态。HTTP 权限校验和 Celery 消息接收分别由 API Service 与 Worker 入口负责。
"""

import logging

from app.agents.requirement_analysis_graph import (
    REQUIREMENT_EXTRACTION_GRAPH,
    RequirementAnalysisContext,
    RequirementAnalysisState,
)
from app.agents.requirement_analysis_schemas import (
    ExtractedRequirementItem,
    RequirementExtractionOutput,
)
from app.core.constants import (
    AIModelTaskType,
    RequirementExtractionStage,
    RequirementExtractionTaskStatus,
    RequirementStatus,
)
from app.exceptions import (
    BadRequestException,
    BusinessException,
    ConflictException,
    ExternalServiceException,
    InternalServerException,
)
from app.models import (
    AIModel,
    KnowledgeDocumentChunk,
    PromptTemplate,
    RequirementExtractionTask,
    RequirementItem,
)
from app.models.mixins import utc_now
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.requirement_extraction_tasks_repository import RequirementExtractionTasksRepository
from app.repositories.requirement_items_repository import RequirementItemsRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.schemas.dto.ai_usage_logs import AIUsageContextDTO

logger = logging.getLogger(__name__)

class RequirementExtractionExecutionService:
    """协调一次后台需求拆解任务涉及的数据库、模型和 Graph 操作。

    功能：领取 Celery 对应的业务任务，加载稳定的需求输入和 AI 配置，执行需求
    拆解 Graph，并在异常时统一保存失败状态。
    作用：位于 Worker 与 Repository/Graph 之间，是异步需求拆解流程的业务编排层；
    Worker 只负责创建依赖并调用 ``execute``，具体阶段推进由本类完成。
    为什么用它：把编排放进 Service 可以避免 Celery Task 同时承担消息队列、业务
    校验和事务处理职责，也便于脱离 Worker 单独测试；它不处理 HTTP 用户权限，
    因为任务提交时 API 层已经完成授权并保存了输入快照。
    """

    def __init__(
            self,
            requirement_extraction_tasks_repository: RequirementExtractionTasksRepository,
            requirements_repository: RequirementsRepository,
            requirement_items_repository: RequirementItemsRepository,
            knowledge_document_repository: KnowledgeDocumentRepository,
            ai_model_repository: AIModelRepository,
            prompt_template_repository: PromptTemplateRepository
    ):
        """注入需求拆解执行过程中需要的数据库访问对象。

        功能：保存任务、需求、需求点、文档、模型和 Prompt Repository。
        作用：后续私有方法通过同一个 Service 实例访问数据，Worker 负责使用同一
        AsyncSession 创建这些 Repository，从而让一次任务处于一致的事务上下文。
        为什么用它：构造器注入能明确依赖并方便测试替换；相比在方法内部创建
        Session 或 Repository，它可以避免同一任务跨多个不受控事务。
        """

        self.requirement_extraction_tasks_repository = requirement_extraction_tasks_repository
        self.requirements_repository = requirements_repository
        self.requirement_items_repository = requirement_items_repository
        self.knowledge_document_repository = knowledge_document_repository
        self.ai_model_repository = ai_model_repository
        self.prompt_template_repository = prompt_template_repository

    async def _load_requirement_text(
            self,
            task: RequirementExtractionTask,
    ) -> tuple[str, dict[int, KnowledgeDocumentChunk]]:
        """根据任务输入快照加载本次拆解使用的稳定需求正文。

        功能：支持从需求摘要或已索引文档读取正文；文档来源会按 ``chunk_index``
        排序并添加 chunk_id、页码、章节等来源标记，同时返回切片 ID 映射。
        作用：为 LangGraph 准备 ``requirement_text``，并为后续来源白名单校验提供
        ``source_chunks``；该方法在任何模型调用发生前执行。
        为什么用它：任务提交后原需求或文档可能被修改，所以根据 input_snapshot
        中记录的来源和文档版本读取，能够保证异步执行与提交时语义一致。保留来源
        标记可要求 AI 返回可追溯的 chunk_id；一次性返回正文和映射则避免重复查询。
        """

        # input_snapshot 是 API 提交任务时固化的 JSON，而不是执行时重新读取的
        # 可变前端参数；它决定本次任务按摘要还是按关联文档进行拆解。
        snapshot = task.input_snapshot
        source_type = snapshot.get("source_type")

        if source_type == "SUMMARY":
            # 未关联知识文档时使用需求自身摘要。摘要没有知识切片，因此返回空的
            # source_chunks，模型也不应生成任何来源切片 ID。
            summary = snapshot.get("summary")

            if not isinstance(summary, str):
                raise InternalServerException("需求拆解任务中的摘要格式错误")

            requirement_text = summary.strip()
            source_chunks: dict[int, KnowledgeDocumentChunk] = {}
        elif source_type == "DOCUMENT":
            # 文档 ID 和版本共同定位任务提交时看到的那一版文档，防止排队期间
            # 文档被替换后，旧任务在不知情的情况下分析新内容。
            document_id = snapshot.get("document_id")
            document_version = snapshot.get("document_version")
            if not isinstance(document_id, int):
                raise InternalServerException("需求拆解任务缺少文档 ID")

            if not isinstance(document_version, int):
                raise InternalServerException("需求拆解任务缺少文档版本")
            document = (
                await self.knowledge_document_repository.get_document_for_extraction(
                    task.project_id,
                    document_id,
                    document_version,
                )
            )

            if document is None:
                raise ConflictException("需求文档不存在、已停用或版本已经变化")

            ordered_chunks = sorted(
                document.chunks,
                key=lambda chunk: chunk.chunk_index,
            )
            # document_parts 负责拼接发送给模型的文本；source_chunks 保存
            # “切片 ID → ORM 切片”映射，后续既能生成白名单，也能定位页码和章节。
            document_parts: list[str] = []
            source_chunks = {}
            for chunk in ordered_chunks:
                content = chunk.content.strip()

                # 空切片没有分析价值，跳过后也不会进入合法来源 ID 白名单。
                if not content:
                    continue

                # 每段正文使用明确的开始/结束标记包围。AI 可以引用 chunk_id，
                # 程序随后能验证该 ID，避免只返回无法追溯的自然语言结论。
                marker_parts = [
                    f"chunk_id={chunk.id}",
                ]
                if chunk.page_no is not None:
                    marker_parts.append(

                        f"page_no={chunk.page_no}"
                    )
                if chunk.section_title:
                    section_title = (
                        chunk.section_title.strip().replace("\n"," ")
                    )
                    marker_parts.append(
                        f"section={section_title}"
                    )
                source_marker = " ".join(marker_parts)
                document_parts.append(
                    f"--- SOURCE_START {source_marker} ---\n"
                    f"{content}\n"
                    f"--- SOURCE_END chunk_id={chunk.id} ---"
                )
                source_chunks[chunk.id] = chunk

            requirement_text = "\n\n".join(document_parts)
        else:
            raise InternalServerException("需求拆解任务的来源类型不受支持")

        if not requirement_text:
            raise BadRequestException("没有可供 AI 拆解的需求正文")

        # 同时返回正文和切片映射，让调用方不需要再次查询同一份文档。
        return requirement_text,source_chunks

    async def _load_ai_configuration(
            self,
    ) -> tuple[AIModel, PromptTemplate]:
        """读取并校验本次需求拆解必须使用的模型与 Prompt。

        功能：取得默认模型和 ``requirement_analysis`` 模板，并检查模型、服务商、
        任务类型和模板启用状态。
        作用：在启动 Graph 前建立完整运行 Context，确保节点不会在执行中途才发现
        缺少配置，同时把实际模型和 Prompt ID 记录到任务审计字段。
        为什么用它：集中做前置校验可以提供明确业务错误，避免把配置问题表现为
        底层 SDK 异常。使用数据库配置而非代码硬编码，允许管理员切换模型和 Prompt；
        但系统仍用固定业务编码查找模板，以保证运行时变量契约稳定。
        """

        ai_model = await self.ai_model_repository.get_default_model()
        if ai_model is None:
            raise InternalServerException("未配置默认需求分析模型")
        if not ai_model.enabled:
            raise InternalServerException("默认需求分析模型已停用")
        if not ai_model.provider.enabled:
            raise InternalServerException("默认需求分析模型的服务商已停用")
        if AIModelTaskType.REQUIREMENT_ANALYSIS.value not in ai_model.task_types:
            raise InternalServerException("默认模型不支持需求分析")
        prompt_template = (
            await self.prompt_template_repository.get_by_code(
                "requirement_analysis"
            )
        )
        if prompt_template is None:
            raise InternalServerException("未配置需求分析 Prompt 模板")
        if not prompt_template.enabled:
            raise InternalServerException("需求分析 Prompt 模板已停用")
        return ai_model, prompt_template

    async def _mark_failed(
            self,
            project_id:int,
            requirement_id:int,
            task_id:int,
            exc:Exception
    ):
        """在主流程异常后安全地保存任务和需求的失败状态。

        功能：回滚原事务，重新查询并锁定需求和任务，将仍在运行中的任务更新为
        FAILED，同时保存脱敏错误摘要和结束时间。
        作用：作为 ``execute`` 的统一异常收口，保证模型、校验或数据库任一步失败
        后，前端不会永久看到 RUNNING；它只处理当前任务对应的业务记录。
        为什么用它：原异常可能已使 Session 事务失效，因此必须先 rollback 再查询；
        加行锁可以避免取消、重复 Worker 等并发操作相互覆盖。未知异常只保存类型，
        不保存完整堆栈或输入正文，以减少敏感信息泄露。
        """

        # 主流程可能在 flush/commit 中失败，先回滚才能让同一个 Session 重新查询。
        await self.requirement_extraction_tasks_repository.rollback()
        # 同时锁定需求与任务，后续状态判断和修改在同一个事务中完成。
        requirement = await self.requirements_repository.get_requirement_detail(
            project_id, requirement_id, lock=True
        )
        task = await self.requirement_extraction_tasks_repository.get_task(
            project_id,requirement_id,task_id,lock=True
        )
        if task is None:
            # 任务本身已经不存在时没有可更新对象；回滚用于释放可能取得的行锁。
            await self.requirement_extraction_tasks_repository.rollback()
            return
        if task.status != RequirementExtractionTaskStatus.RUNNING.value:
            # 只把仍在运行的任务改为失败，避免覆盖其他并发流程已经写入的
            # COMPLETED、FAILED 或 CANCELLED 最终状态。
            await self.requirement_extraction_tasks_repository.rollback()
            return
        # 主动抛出的业务异常可以安全展示其 message；未知异常只记录异常类型，
        # 详细堆栈保留在服务日志中。
        if isinstance(exc,BusinessException):
            task.error_message = exc.message
        else:
            task.error_message = f"需求拆解执行失败：{type(exc).__name__}"
        task.status = RequirementExtractionTaskStatus.FAILED.value
        task.finished_at = utc_now()
        # 即使需求已被软删除，任务记录仍应进入 FAILED，避免永远停在 RUNNING；
        # 只有需求仍存在且处于本任务控制的 EXTRACTING 状态时才同步修改需求。
        if (
                requirement is not None
                and requirement.status == RequirementStatus.EXTRACTING.value
        ):
            requirement.status = RequirementStatus.FAILED.value
            requirement.updated_at = utc_now()
        await self.requirement_extraction_tasks_repository.commit()

    async def _replace_unconfirmed_ai_items(
            self,
            requirement_id: int,
    ) -> int:
        """安全删除上一批尚未人工确认的 AI 需求点。

        功能：锁定当前需求的完整需求点树，找出 ``ai_generated=True`` 且尚未确认
        的节点；先把需要保留的人工或已确认节点重新挂到最近的保留祖先，再批量
        删除可替换节点，并返回删除数量。
        作用：在写入新一批 AI 拆解结果前清理旧草稿，同时保证人工审核成果不会
        因父节点的 ``ON DELETE CASCADE`` 被误删。
        为什么用它：直接按条件 DELETE 无法感知树关系，删除未确认父节点可能级联
        删除已确认子节点。先在锁定快照中重建保留关系并 flush，再执行批量删除，
        可以兼顾数据安全、并发一致性和 SQL 数量。
        """

        existing_items = (
            await self.requirement_items_repository.list_items_for_update(
                requirement_id
            )
        )
        if not existing_items:
            return 0

        items_by_id = {item.id: item for item in existing_items}
        replaceable_ids = {
            item.id
            for item in existing_items
            if item.ai_generated and not item.confirmed
        }
        if not replaceable_ids:
            return 0

        def find_nearest_retained_parent(
                parent_id: int | None,
        ) -> int | None:
            """沿旧父链向上寻找不会被本次替换删除的最近祖先。

            功能：跳过所有待删除父级，返回最近的保留节点 ID；不存在则返回 None。
            作用：供外层循环重新挂接已确认或人工节点，避免删除旧 AI 父级时触发
            数据库级联删除。
            为什么用它：需求点层级深度不固定，使用循环比只检查直接父级可靠；
            visited 还能防御历史脏数据中的循环关系，防止后台任务无限循环。
            """

            current_parent_id = parent_id
            visited: set[int] = set()
            while current_parent_id in replaceable_ids:
                if current_parent_id in visited:
                    return None
                visited.add(current_parent_id)
                parent_item = items_by_id.get(current_parent_id)
                if parent_item is None:
                    return None
                current_parent_id = parent_item.parent_id

            # 正常数据的父级一定属于同一需求；若历史数据指向范围外记录，落到
            # 顶层比继续保留跨需求父级更安全。
            if (
                    current_parent_id is not None
                    and current_parent_id not in items_by_id
            ):
                return None
            return current_parent_id

        for existing_item in existing_items:
            if existing_item.id in replaceable_ids:
                continue
            if existing_item.parent_id not in replaceable_ids:
                continue
            existing_item.parent_id = find_nearest_retained_parent(
                existing_item.parent_id
            )

        # 必须先把保留节点的新 parent_id 写入数据库，再删除旧父级；否则数据库
        # 仍会按旧外键执行 ON DELETE CASCADE。
        await self.requirement_items_repository.flush()
        await self.requirement_items_repository.delete_items_by_ids(
            requirement_id,
            replaceable_ids,
        )
        await self.requirement_items_repository.flush()
        return len(replaceable_ids)

    @staticmethod
    def _build_source_locator(
            extracted_item: ExtractedRequirementItem,
            source_chunks: dict[int, KnowledgeDocumentChunk],
            source_type: str,
            extraction_task_id: int,
    ) -> dict[str, object]:
        """把模型引用转换为可供前端追溯的来源定位快照。

        功能：根据已校验的 source_chunk_ids，保存每个切片的文档 ID、序号、页码、
        章节以及模型引用原文，并附带任务 ID 和模型临时编号。
        作用：写入 ``RequirementItem.source_locator``，人工审核需求点时可返回原文
        位置，后续覆盖分析和审计也能追踪该需求点来自哪次模型拆解。
        为什么用它：只保存 ORM 外键无法保留生成当时的页码和章节快照；JSONB 能
        容纳摘要来源与文档来源的不同结构。这里不保存完整切片正文，避免重复数据
        过大和需求原文泄露，只保留短引用及定位元数据。
        """

        sources: list[dict[str, object]] = []
        for chunk_id in extracted_item.source_chunk_ids:
            chunk = source_chunks.get(chunk_id)
            # Graph 已经做过白名单校验；这里仍允许缺失时跳过，避免来源文档在
            # 模型调用后发生变化导致直接访问 None 属性。
            if chunk is None:
                continue
            sources.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "page_no": chunk.page_no,
                    "section_title": chunk.section_title,
                }
            )

        return {
            "source_type": source_type,
            "extraction_task_id": extraction_task_id,
            "local_id": extracted_item.local_id,
            "source_quote": extracted_item.source_quote,
            "sources": sources,
        }

    async def _save_extracted_items(
            self,
            requirement_id: int,
            extraction_task_id: int,
            extraction_output: RequirementExtractionOutput,
            source_chunks: dict[int, KnowledgeDocumentChunk],
            source_type: str,
    ) -> list[RequirementItem]:
        """分两个阶段保存模型生成的全部需求点及父子关系。

        功能：第一阶段创建所有 parent_id 为空的 RequirementItem 并 flush 取得主键；
        第二阶段通过 ``local_id → ORM 实体`` 映射设置真实 parent_id，再次 flush。
        作用：把 Graph 的临时结构化结果转换为可人工编辑、确认和关联用例的数据库
        记录，返回实体列表供主流程统计并写入任务输出快照。
        为什么用它：AI 不保证父节点一定出现在子节点之前，直接逐条设置数据库
        parent_id 会依赖输出顺序。两阶段保存只需要两次批量 flush，既消除顺序依赖，
        也比为每个父节点单独查询数据库更高效。
        """

        entities: list[RequirementItem] = []
        entities_by_local_id: dict[str, RequirementItem] = {}

        # 第一阶段：先创建所有行但暂不设置父级。Pydantic 已保证 local_id 唯一，
        # 因此可以安全作为本次模型输出的临时映射键。
        for order_no, extracted_item in enumerate(extraction_output.items):
            entity = RequirementItem(
                requirement_id=requirement_id,
                parent_id=None,
                # 数据库 item_code 需要跨多次拆解保持唯一；使用任务 ID 和顺序号，
                # 模型自己的 local_id 则原样保存在 source_locator 中用于审计。
                item_code=f"AI-{extraction_task_id}-{order_no + 1}",
                title=extracted_item.title,
                description=extracted_item.description,
                item_type=extracted_item.item_type.value,
                priority=extracted_item.priority.value,
                acceptance_criteria=extracted_item.acceptance_criteria,
                source_locator=self._build_source_locator(
                    extracted_item,
                    source_chunks,
                    source_type,
                    extraction_task_id,
                ),
                ai_generated=True,
                confirmed=False,
                order_no=order_no,
            )
            self.requirement_items_repository.add(entity)
            entities.append(entity)
            entities_by_local_id[extracted_item.local_id] = entity

        # flush 只把 INSERT 发送到数据库并取得主键，不提交事务；后续任一步失败，
        # 外层仍能整体 rollback，不会留下半批数据。
        await self.requirement_items_repository.flush()

        # 第二阶段：Pydantic 已确认父临时编号存在且无环，这里只负责把临时编号
        # 翻译成数据库生成的整数主键。
        for extracted_item, entity in zip(
                extraction_output.items,
                entities,
                strict=True,
        ):
            if extracted_item.parent_local_id is None:
                continue
            parent_entity = entities_by_local_id[
                extracted_item.parent_local_id
            ]
            entity.parent_id = parent_entity.id

        await self.requirement_items_repository.flush()
        return entities

    async def execute(
            self,
            extraction_task_id: int,
            celery_task_id: str,
    ) -> bool:
        """领取并执行一条 Celery 需求拆解业务任务。

        功能：原子领取任务，加载需求正文与 AI 配置，创建 Graph State/Context，执行
        模型拆解和结构校验，并把所有异常交给失败状态处理方法。
        作用：这是 Worker 调用的主入口。返回 False 表示任务无需重复执行；成功路径
        将继续使用 ``extraction_output`` 保存需求点并推进任务状态。
        为什么用它：数据库任务与 Celery 消息是两个系统，先通过 ``claim_task``
        校验状态和 celery_task_id 可以实现幂等消费，防止重复投递产生重复需求点；
        主流程统一放在 try/except 中，确保任何阶段失败都能持久化终态。
        """

        # claim_task 使用数据库状态和 Celery ID 原子领取任务。只有成功把 PENDING
        # 推进到 RUNNING 的 Worker 才会继续执行。
        task = await self.requirement_extraction_tasks_repository.claim_task(
            extraction_task_id, celery_task_id
        )
        # 这里返回 False 的情况包括：
        # - 数据库任务不存在。
        # - Celery 任务 ID 不匹配。
        # - 任务已经被其他 Worker 领取。
        # - 任务已经成功、失败或取消。
        if task is None:
            return False
        # 提前保存基础 ID。后续 commit/rollback 可能改变 ORM 对象状态，而失败
        # 处理始终可以依靠这些不可变整数重新查询对应记录。
        task_id = task.id
        project_id = task.project_id
        requirement_id = task.requirement_id
        try:
            # 第一阶段：恢复任务提交时的稳定输入，并完成模型与 Prompt 前置校验。
            requirement_text, source_chunks = await self._load_requirement_text(task)
            ai_model, prompt_template = (
                await self._load_ai_configuration()
            )
            task.model_id = ai_model.id
            task.prompt_template_id = prompt_template.id
            task.current_stage = RequirementExtractionStage.CALLING_MODEL.value
            task.progress = 20

            # 先提交阶段和实际配置，长时间模型调用期间前端即可看到真实进度；
            # 即使进程中断，也能从任务记录判断停在哪个阶段。
            await self.requirement_extraction_tasks_repository.commit()
            # 统一 AI 工具使用该上下文记录调用人、项目和 Celery 任务，便于按业务
            # 链路查询 Token、耗时和失败日志。
            usage_context = AIUsageContextDTO(
                user_id=task.requested_by,
                project_id=project_id,
                task_id=celery_task_id,
            )
            initial_state: RequirementAnalysisState = {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "requirement_text": requirement_text,
                "allowed_source_chunk_ids": list(source_chunks),
                "validation_errors": [],
                "validation_feedback": "",
                "retry_count": 0,
                "extraction_output": None,
            }
            # Context 保存节点运行工具；State 只保存本次流程数据。二者分离后，
            # 节点返回值不会意外覆盖 Repository、模型或 Prompt 对象。
            graph_context = RequirementAnalysisContext(
                ai_model_repository=self.ai_model_repository,
                ai_model=ai_model,
                prompt_template=prompt_template,
                usage_context=usage_context,
            )
            graph_result = await REQUIREMENT_EXTRACTION_GRAPH.ainvoke(
                initial_state,
                context=graph_context,
            )
            extraction_output = graph_result.get(
                "extraction_output"
            )
            # success 与 failed 路线都会正常到达 END，所以不能仅凭 ainvoke 返回
            # 判断成功；必须确认 Graph 最终产生了经过 Pydantic 校验的对象。
            if not isinstance(extraction_output,RequirementExtractionOutput):
                validation_errors = graph_result.get(
                    "validation_errors",
                    [],
                )

                error_detail = "；".join(
                    str(error)
                    for error in validation_errors[:5]
                )

                message = "需求分析模型多次返回不符合约定的结构"

                # 只保留最多五条确定性的校验错误，不把可能很长且含业务正文的
                # raw_output 写入任务错误字段。
                if error_detail:
                    message = f"{message}：{error_detail}"

                raise ExternalServiceException(message)

            # 模型和校验已经完成，先持久化“保存需求点”阶段。数据库写入通常很快，
            # 但这次提交能让前端区分模型仍在生成与结果已经进入落库阶段。
            task.current_stage = RequirementExtractionStage.SAVING_ITEMS.value
            task.progress = 80
            await self.requirement_extraction_tasks_repository.commit()

            # 模型调用耗时较长，期间需求可能被编辑、归档或任务可能被取消。
            # 最终写入前重新查询并加锁，所有快照复核、替换和新增都在同一事务中。
            requirement = await self.requirements_repository.get_requirement_detail(
                project_id,
                requirement_id,
                lock=True,
            )
            locked_task = (
                await self.requirement_extraction_tasks_repository.get_task(
                    project_id,
                    requirement_id,
                    task_id,
                    lock=True,
                )
            )
            if locked_task is None:
                raise InternalServerException("需求拆解任务在保存结果前不存在")
            if locked_task.status != RequirementExtractionTaskStatus.RUNNING.value:
                # 任务已被取消或被其他流程写入终态时，不再覆盖对方结果。
                await self.requirement_extraction_tasks_repository.rollback()
                return False
            if requirement is None:
                raise ConflictException("需求已被删除，拆解结果不再保存")
            if requirement.status != RequirementStatus.EXTRACTING.value:
                raise ConflictException("需求状态已经变化，拆解结果不再保存")

            snapshot = locked_task.input_snapshot
            expected_requirement_version = snapshot.get(
                "requirement_version"
            )
            if not isinstance(expected_requirement_version, str):
                raise InternalServerException("需求拆解任务缺少需求版本快照")
            if requirement.version != expected_requirement_version:
                raise ConflictException("需求版本已经变化，请重新提交拆解任务")

            source_type = snapshot.get("source_type")
            if not isinstance(source_type, str):
                raise InternalServerException("需求拆解任务缺少来源类型")
            if source_type == "DOCUMENT":
                expected_document_id = snapshot.get("document_id")
                expected_document_version = snapshot.get("document_version")
                if (
                        requirement.document is None
                        or requirement.document_id != expected_document_id
                        or requirement.document.version != expected_document_version
                ):
                    raise ConflictException(
                        "关联需求文档已经变化，请重新提交拆解任务"
                    )

            replace_unconfirmed_ai_items = snapshot.get(
                "replace_unconfirmed_ai_items",
                True,
            )
            if not isinstance(replace_unconfirmed_ai_items, bool):
                raise InternalServerException("需求拆解任务的替换选项格式错误")

            replaced_item_count = 0
            if replace_unconfirmed_ai_items:
                replaced_item_count = (
                    await self._replace_unconfirmed_ai_items(
                        requirement_id
                    )
                )

            saved_items = await self._save_extracted_items(
                requirement_id=requirement_id,
                extraction_task_id=task_id,
                extraction_output=extraction_output,
                source_chunks=source_chunks,
                source_type=source_type,
            )

            finished_at = utc_now()
            # output_snapshot 保存已经通过程序校验的结构化结果和本次落库统计，
            # 不保存可能包含完整业务原文的模型 raw_output。
            locked_task.output_snapshot = {
                "result": extraction_output.model_dump(mode="json"),
                "saved_item_count": len(saved_items),
                "replaced_item_count": replaced_item_count,
                "retry_count": int(graph_result.get("retry_count", 0)),
            }
            locked_task.status = RequirementExtractionTaskStatus.COMPLETED.value
            locked_task.current_stage = RequirementExtractionStage.FINISHED.value
            locked_task.progress = 100
            locked_task.error_message = None
            locked_task.finished_at = finished_at

            # 新生成项默认未确认，因此需求进入 REVIEWING，等待测试人员人工校正、
            # 确认后再由需求点 Service 推进到 CONFIRMED。
            requirement.status = RequirementStatus.REVIEWING.value
            requirement.updated_at = finished_at
            await self.requirement_extraction_tasks_repository.commit()
            return True

        except Exception as exc:
            # 先尽力把业务任务更新为 FAILED，再重新抛出原异常，使 Celery 自身也
            # 记录失败。失败状态落库异常不能覆盖最初的业务异常。
            try:
                await self._mark_failed(project_id,requirement_id,task_id,exc)
            except Exception:
                logger.exception("失败状态落库失败")
            raise


