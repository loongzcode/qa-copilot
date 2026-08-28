from celery import Celery

# 导入指标模块会注册 Celery task_prerun、task_postrun 和 task_retry 信号。
# 业务任务无需逐个重复埋点。
from app.core import metrics as _metrics  # noqa: F401
from app.core.config import settings

# 所有后台任务的固定路由。单独保存队列名称，供 Redis Broker 积压监控复用，
# 避免监控模块再维护一份容易遗漏的新队列清单。
CELERY_TASK_ROUTES = {
    "system.publish_outbox": {"queue": "system-outbox"},
    "system.recover_background_tasks": {"queue": "system-outbox"},
    "knowledge.index_document": {"queue": "knowledge-index"},
    "knowledge.delete_document_file": {"queue": "knowledge-index"},
    "knowledge.compress_chat_memory": {"queue": "knowledge-memory"},
    "requirement.extract_items": {"queue": "requirement-analysis"},
    "case.generate_missing": {"queue": "case-generation"},
    "automation.execute": {"queue": "automation-execution"},
    "automation.dispatch_schedules": {"queue": "system-outbox"},
    "notification.send_automation_result": {"queue": "notifications"},
    "supervisor.execute_run": {"queue": "supervisor-execution"},
}
CELERY_QUEUE_NAMES = tuple(sorted({route["queue"] for route in CELERY_TASK_ROUTES.values()}))


celery_app = Celery(
    "qa_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.knowledge_document_tasks",
        "app.workers.knowledge_chat_memory_tasks",
        "app.workers.requirement_analysis_tasks",
        "app.workers.case_generation_tasks",
        "app.workers.automation_execution_tasks",
        "app.workers.automation_schedule_tasks",
        "app.workers.notification_tasks",
        "app.workers.outbox_tasks",
        "app.workers.supervisor_execution_tasks",
    ],
)

# 索引任务可能包含模型网络调用，使用 late ack 可以避免 Worker 在处理中退出后
# 任务被提前确认。worker_prefetch_multiplier=1 避免单个 Worker 抢占过多长任务。
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 60 * 60},
    result_expires=24 * 60 * 60,
    task_routes=CELERY_TASK_ROUTES,
    beat_schedule={
        "publish-transactional-outbox": {
            "task": "system.publish_outbox",
            "schedule": settings.outbox_publish_interval_seconds,
            # 发布器 Worker 停机时，过期的空轮询任务无需在恢复后逐个补跑。
            "options": {
                "expires": max(
                    settings.outbox_publish_interval_seconds * 2,
                    5,
                )
            },
        },
        "recover-stale-background-tasks": {
            "task": "system.recover_background_tasks",
            "schedule": settings.background_recovery_interval_seconds,
            "options": {
                "expires": max(
                    settings.background_recovery_interval_seconds * 2,
                    30,
                )
            },
        },
        "dispatch-automation-schedules": {
            "task": "automation.dispatch_schedules",
            "schedule": 60,
            "options": {"expires": 55},
        },
    },
)
