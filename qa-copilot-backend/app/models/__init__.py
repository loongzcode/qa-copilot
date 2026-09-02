"""统一导出实体，业务代码无需关心每个实体所在的具体文件。"""

# 先注册中间表，再导入各实体。所有实体导入完成后，SQLAlchemy 才会统一解析字符串关系名。
from app.models.ai_model import AIModel
from app.models.ai_provider import AIProvider
from app.models.ai_usage_log import AIUsageLog
from app.models.associations import role_menu_table, user_role_table
from app.models.automation_definitions import AutomationDefinition, AutomationDefinitionChange
from app.models.automation_execution_step_results import AutomationExecutionStepResult
from app.models.automation_execution_tasks import AutomationExecutionTask
from app.models.automation_schedules import AutomationSchedule
from app.models.data_query import DataQueryExecution, DataSourceMetadataSnapshot, EnvironmentDataSource
from app.models.knowledge_bases import KnowledgeBase
from app.models.knowledge_chat import (
    KnowledgeChatMemorySummary,
    KnowledgeChatMessage,
    KnowledgeChatSession,
)
from app.models.knowledge_document_chunk_staging import KnowledgeDocumentChunkStaging
from app.models.knowledge_document_chunks import KnowledgeDocumentChunk
from app.models.knowledge_documents import KnowledgeDocument
from app.models.menu import Menu
from app.models.notification_channel import NotificationChannel
from app.models.outbox_event import OutboxEvent
from app.models.prompt_template import PromptTemplate
from app.models.requirement_extraction_tasks import RequirementExtractionTask
from app.models.requirements import Requirement, RequirementItem
from app.models.role import Role
from app.models.supervisor import SupervisorPlanStep, SupervisorRun, SupervisorSession
from app.models.test_cases import (
    CaseGenerationTask,
    CaseReviewRecord,
    RequirementCaseLink,
    TestCase,
    TestCaseStep,
)
from app.models.test_environments import TestEnvironment
from app.models.test_modules import TestModule
from app.models.test_project_members import TestProjectMember
from app.models.test_projects import TestProjects
from app.models.tool_center import (
    ExternalConnection,
    FileTemplate,
    ToolApproval,
    ToolArtifact,
    ToolDefinition,
    ToolExecutionLog,
    ToolTask,
)
from app.models.user import User

__all__ = [
    "AIModel",
    "AIProvider",
    "AIUsageLog",
    "AutomationDefinition",
    "AutomationDefinitionChange",
    "AutomationExecutionStepResult",
    "AutomationExecutionTask",
    "AutomationSchedule",
    "EnvironmentDataSource",
    "DataSourceMetadataSnapshot",
    "DataQueryExecution",
    "KnowledgeBase",
    "KnowledgeDocument",
    "KnowledgeDocumentChunk",
    "KnowledgeDocumentChunkStaging",
    "KnowledgeChatMemorySummary",
    "KnowledgeChatMessage",
    "KnowledgeChatSession",
    "Menu",
    "NotificationChannel",
    "OutboxEvent",
    "PromptTemplate",
    "Requirement",
    "RequirementItem",
    "RequirementExtractionTask",
    "Role",
    "SupervisorRun",
    "SupervisorSession",
    "SupervisorPlanStep",
    "TestEnvironment",
    "TestProjectMember",
    "TestProjects",
    "ToolDefinition",
    "ExternalConnection",
    "ToolTask",
    "ToolApproval",
    "ToolExecutionLog",
    "ToolArtifact",
    "FileTemplate",
    "TestCase",
    "TestCaseStep",
    "RequirementCaseLink",
    "CaseGenerationTask",
    "CaseReviewRecord",
    "TestModule",
    "User",
    "role_menu_table",
    "user_role_table",
]
