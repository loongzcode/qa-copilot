"""需求拆解 LangGraph 的 Celery Worker 入口和事件循环生命周期管理。"""
from app.core.celery_app import celery_app
from app.core.database import AsyncSessionFactory
from app.repositories.ai_model_repository import AIModelRepository
from app.repositories.knowledge_document_repository import KnowledgeDocumentRepository
from app.repositories.prompt_template_repository import PromptTemplateRepository
from app.repositories.requirement_extraction_tasks_repository import RequirementExtractionTasksRepository
from app.repositories.requirement_items_repository import RequirementItemsRepository
from app.repositories.requirements_repository import RequirementsRepository
from app.services.requirement_extraction_execution_service import RequirementExtractionExecutionService
from app.workers.async_runtime import run_worker_coroutine


async def _run_requirement_extraction(
        extraction_task_id: int,
        celery_task_id: str,
) -> bool:
    """在独立数据库 Session 中组装并执行需求拆解 Service。

    功能：为一条 Celery 消息创建 AsyncSession、各 Repository 和执行 Service，
    最终调用 ``execute`` 返回任务是否真正被处理。
    作用：隔离同步 Celery 入口与异步业务依赖组装，确保任务结束后 Session 自动
    关闭，并让所有 Repository 共用同一事务上下文。
    为什么用它：后台任务没有 FastAPI 的请求级依赖注入，必须显式组装依赖；
    ``async with`` 无论成功或异常都会释放 Session，避免连接泄漏。
    """

    async with AsyncSessionFactory() as session:
        service = RequirementExtractionExecutionService(
            requirement_extraction_tasks_repository=RequirementExtractionTasksRepository(session),
            requirements_repository=RequirementsRepository(session),
            requirement_items_repository=RequirementItemsRepository(session),
            knowledge_document_repository=KnowledgeDocumentRepository(session),
            ai_model_repository=AIModelRepository(session),
            prompt_template_repository=PromptTemplateRepository(session)
        )
        return await service.execute(extraction_task_id, celery_task_id)


@celery_app.task(
    bind=True,
    name="requirement.extract_items",
)
def extract_requirement_items_task(
        self,
        extraction_task_id:int,
):
    """接收 Celery 消息并桥接到异步需求拆解主流程。

    功能：读取 Celery 自身任务 ID，与数据库任务主键一起传给异步执行方法。
    作用：注册为 ``requirement.extract_items``，由 Dispatcher 投递并由专用队列的
    Worker 消费；数据库中的 celery_task_id 会阻止错误或重复消息领取任务。
    为什么用它：使用 bind=True 才能取得 ``self.request.id``，从而把消息队列任务
    与数据库审计记录稳定关联；同步入口通过复用事件循环运行异步代码。
    """

    celery_task_id = str(self.request.id)

    return run_worker_coroutine(
        _run_requirement_extraction(
            extraction_task_id,
            celery_task_id,
        )
    )
