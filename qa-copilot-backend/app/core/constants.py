from enum import IntEnum, StrEnum

# PostgreSQL 的知识切片向量列是 vector(1536)，模型调用和入库校验必须使用
# 同一个维度，避免三个位置分别写数字后出现配置漂移。
KNOWLEDGE_EMBEDDING_DIMENSIONS = 1536

# 当前文档切片、全文字段和向量的生成规则版本。修改切片算法、清洗规则或向量
# 预处理方式时递增该值，并对旧文档执行完整重建。
KNOWLEDGE_DOCUMENT_INDEX_VERSION = 1


class ErrorCode(StrEnum):
    """集中保存前后端约定的错误码，避免在各个文件里散落字符串。"""

    INVALID_CREDENTIALS = "1001"
    REFRESH_TOKEN_INVALID = "8888"
    UNAUTHORIZED = "9999"
    BAD_REQUEST = "400"
    FORBIDDEN = "403"
    NOT_FOUND = "404"
    CONFLICT = "409"
    VALIDATION_ERROR = "4220"
    INTERNAL_SERVER_ERROR = "5000"
    EXTERNAL_SERVICE_ERROR = "502"


class HttpStatusConstant(IntEnum):
    """统一响应状态码及其默认中文消息。"""

    # 成功状态
    SUCCESS = (200, "操作成功")
    CREATED = (201, "对象创建成功")
    ACCEPTED = (202, "请求已接受")
    NO_CONTENT = (204, "操作成功，无返回数据")

    # 重定向状态
    MOVED_PERM = (301, "资源已被永久移除")
    SEE_OTHER = (303, "请访问其他地址")
    NOT_MODIFIED = (304, "资源未修改")

    # 客户端错误状态
    BAD_REQUEST = (400, "请求参数错误")
    UNAUTHORIZED = (401, "未登录或登录状态已过期")
    FORBIDDEN = (403, "没有访问权限")
    NOT_FOUND = (404, "请求资源不存在")
    BAD_METHOD = (405, "不支持当前请求方法")
    CONFLICT = (409, "资源冲突或已被锁定")
    UNSUPPORTED_TYPE = (415, "不支持当前数据或媒体类型")

    # 服务端和业务状态
    ERROR = (500, "系统内部错误")
    NOT_IMPLEMENTED = (501, "接口尚未实现")
    WARN = (601, "系统警告")

    message: str

    def __new__(cls, code: int, message: str):
        """使用整数作为枚举值，并为枚举成员保存默认中文消息。"""
        member = int.__new__(cls, code)
        member._value_ = code
        member.message = message
        return member

    @property
    def code(self) -> int:
        """返回用于统一响应体的数字状态码。"""
        return self.value


class ProjectMemberRole(StrEnum):
    """项目内成员角色；角色决定项目资产的业务操作范围。"""

    # 项目负责人角色，拥有项目内最高业务管理权限。
    OWNER = "OWNER"
    # 项目管理员，可以协助维护项目资产和成员。
    MANAGER = "MANAGER"
    # 普通项目成员，可以参与项目测试工作。
    MEMBER = "MEMBER"
    # 只读成员，只能查看被授权的项目资产。
    VIEWER = "VIEWER"


class ProjectStatus(StrEnum):
    """测试项目生命周期状态。"""

    # 未开始：项目仍在准备阶段，可以继续配置成员、模块和环境。
    DRAFT = "DRAFT"
    # 进行中：项目已经启动，可以开展正常测试工作。
    ACTIVE = "ACTIVE"
    # 已归档：仅允许查看历史资产，禁止继续修改项目业务数据。
    ARCHIVED = "ARCHIVED"


class KnowledgeVisibility(StrEnum):
    """知识库可见范围。"""

    # 当前项目的负责人、管理员、普通成员和只读成员均可查看。
    PROJECT = "PROJECT"
    # 只有项目负责人以及 OWNER、MANAGER 角色成员可以查看。
    MANAGERS = "MANAGERS"
    # 只有知识库创建者可以查看；超级管理员仍可按平台规则查看。
    PRIVATE = "PRIVATE"


class KnowledgeDocumentType(StrEnum):
    """知识文档的业务分类，用于检索过滤和限定回答范围。"""

    # 已沉淀并通过评审的标准测试用例。
    STANDARD_CASE = "STANDARD_CASE"
    # 企业或项目测试流程、规范和检查清单。
    TEST_PROCESS = "TEST_PROCESS"
    # 系统、平台或业务功能的操作说明。
    OPERATION_GUIDE = "OPERATION_GUIDE"
    # 系统架构、模块设计和技术方案文档。
    SYSTEM_DESIGN = "SYSTEM_DESIGN"
    # 产品需求、业务需求和变更说明。
    REQUIREMENT = "REQUIREMENT"
    # OpenAPI、接口约定和调用示例等接口资料。
    API_DOCUMENT = "API_DOCUMENT"
    # 历史缺陷原因、排查过程和解决经验。
    DEFECT_EXPERIENCE = "DEFECT_EXPERIENCE"
    # 暂时无法归入上述分类的其他知识。
    OTHER = "OTHER"


class KnowledgeDocumentSourceType(StrEnum):
    """知识文档内容进入平台的来源。"""

    # 用户上传 PDF、DOCX、Markdown 或 TXT 文件。
    UPLOAD = "UPLOAD"
    # 平台根据外部网页地址采集内容。
    URL = "URL"
    # 用户直接在平台编辑器中录入内容。
    MANUAL = "MANUAL"
    # 从其他系统或批量数据包导入。
    IMPORT = "IMPORT"


class KnowledgeDocumentParseStatus(StrEnum):
    """知识文档从入库到可检索的处理状态。"""

    # 已保存文档元数据和原始文件，等待异步任务处理。
    PENDING = "PENDING"
    # 正在从 PDF、DOCX 等原始文件中提取文本。
    PARSING = "PARSING"
    # 正在切片、生成 Embedding 并写入检索索引。
    INDEXING = "INDEXING"
    # 解析和索引均完成，文档已经可以参与知识检索。
    READY = "READY"
    # 处理失败，可根据 error_message 排查并重新提交任务。
    FAILED = "FAILED"


class OutboxEventStatus(StrEnum):
    """事务性发件箱事件从创建到成功发布的生命周期状态。"""

    # 业务事务已经保存事件，等待发布器投递到消息队列。
    PENDING = "PENDING"
    # 发布器已经认领事件，防止多个发布器同时发送同一条消息。
    PROCESSING = "PROCESSING"
    # 本次发布失败但仍可重试，等待 available_at 到期后再次投递。
    RETRY = "RETRY"
    # 消息已经成功发布到 Celery Broker。
    PUBLISHED = "PUBLISHED"
    # 重试次数已经耗尽，需要人工排查或重新创建事件。
    FAILED = "FAILED"


class OutboxEventType(StrEnum):
    """发件箱支持的业务事件类型；发布器据此选择对应的 Celery 任务。"""

    # 请求后台解析知识文档、生成切片与向量索引。
    KNOWLEDGE_DOCUMENT_INDEX = "KNOWLEDGE_DOCUMENT_INDEX"
    # 请求后台删除知识文档对应的原始存储对象。
    KNOWLEDGE_DOCUMENT_FILE_DELETE = "KNOWLEDGE_DOCUMENT_FILE_DELETE"
    # 请求后台运行一条已持久化的自动化执行任务。
    AUTOMATION_EXECUTION = "AUTOMATION_EXECUTION"
    # 自动化任务进入最终状态后，请求后台发送结果通知。
    AUTOMATION_RESULT_NOTIFICATION = "AUTOMATION_RESULT_NOTIFICATION"
    # 请求后台按依赖顺序执行一条已通过安全校验的 Supervisor 运行。
    SUPERVISOR_EXECUTION = "SUPERVISOR_EXECUTION"


class OutboxAggregateType(StrEnum):
    """产生发件箱事件的业务对象类型。"""

    # 知识库原始文档。
    KNOWLEDGE_DOCUMENT = "KNOWLEDGE_DOCUMENT"
    # 一次自动化执行任务。
    AUTOMATION_EXECUTION = "AUTOMATION_EXECUTION"
    # 一次已经持久化的 Supervisor 运行。
    SUPERVISOR_RUN = "SUPERVISOR_RUN"


class ToolRisk(StrEnum):
    """工具操作风险等级；决定是否必须人工审批。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CapabilityInvocationSource(StrEnum):
    """受控能力的调用来源；校验器据此应用不同的暴露规则。"""

    # Supervisor Agent 在应用内部编排业务能力。
    SUPERVISOR = "SUPERVISOR"
    # Model Context Protocol（模型上下文协议）客户端从应用外部请求能力。
    MCP = "MCP"


class SupervisorStepDecision(StrEnum):
    """Supervisor 计划步骤经过确定性安全校验后的处理决定。"""

    # 权限、来源和依赖均合法，可以进入后续执行阶段。
    READY = "READY"
    # 步骤本身合法，但必须经过人工审批才能执行。
    BLOCKED_APPROVAL = "BLOCKED_APPROVAL"
    # 工具不存在、权限不足或依赖非法，禁止执行。
    REJECTED = "REJECTED"


class SupervisorRunStatus(StrEnum):
    """一次 Supervisor 目标从规划到结束的持久化状态。"""

    PLANNING = "PLANNING"
    PLAN_REJECTED = "PLAN_REJECTED"
    READY = "READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SupervisorExecutionStepStatus(StrEnum):
    """Supervisor 计划步骤在数据库中的执行状态。"""

    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"
    READY = "READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class SupervisorApprovalDecision(StrEnum):
    """人工对 Supervisor 中高风险步骤作出的不可重复决定。"""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ToolConnectionType(StrEnum):
    """测试工具中心支持的外部系统连接类型。"""

    MYSQL = "MYSQL"
    NACOS = "NACOS"
    BUSINESS_API = "BUSINESS_API"
    DEFECT_PLATFORM = "DEFECT_PLATFORM"


class ToolTaskType(StrEnum):
    """统一工具任务类型。"""

    FILE_GENERATE = "FILE_GENERATE"
    FILE_VALIDATE = "FILE_VALIDATE"
    MYSQL_COMPARE = "MYSQL_COMPARE"
    MYSQL_SYNC = "MYSQL_SYNC"
    NACOS_COMPARE = "NACOS_COMPARE"
    NACOS_SYNC = "NACOS_SYNC"
    DEFECT_SYNC = "DEFECT_SYNC"
    UI_AUTOMATION = "UI_AUTOMATION"


class UIAutomationAction(StrEnum):
    """Playwright 受控 UI 自动化允许的动作。"""

    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    FILL = "FILL"
    ASSERT_VISIBLE = "ASSERT_VISIBLE"
    ASSERT_TEXT = "ASSERT_TEXT"
    ASSERT_URL = "ASSERT_URL"


class ToolTaskStatus(StrEnum):
    """工具任务从预览到执行、回滚的完整状态。"""

    DRAFT = "DRAFT"
    PREVIEWED = "PREVIEWED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class ToolApprovalDecision(StrEnum):
    """高风险工具任务的人工审批决定。"""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FileTemplateFormat(StrEnum):
    """账务文件模板支持的输出格式。"""

    CSV = "CSV"
    EXCEL = "EXCEL"
    FIXED_WIDTH_TXT = "FIXED_WIDTH_TXT"
    DELIMITED_TXT = "DELIMITED_TXT"
    JSON = "JSON"
    XML = "XML"


class MenuType(StrEnum):
    DIRECTORY = "directory"
    PAGE = "page"
    BUTTON = "button"


class AIProviderType(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_COMPATIBLE = "openai_compatible"


class AIModelTaskType(StrEnum):
    """AI 模型支持的业务任务类型。"""

    # 为文档切片生成向量。
    EMBEDDING = "embedding"
    # 对知识检索候选结果重新排序。
    RERANK = "rerank"
    # 根据知识库检索结果回答问题。
    KNOWLEDGE_QA = "knowledge_qa"
    # 分析缺陷内容及可能原因。
    DEFECT_ANALYSIS = "defect_analysis"
    # 审查测试资产的完整性和质量。
    TEST_REVIEW = "test_review"
    # 根据需求或上下文生成测试用例。
    TEST_CASE_GENERATION = "test_case_generation"
    # 根据会话历史，把含有指代或省略的追问改写成可独立检索的问题。
    QUERY_REWRITE = "query_rewrite"
    # 将原始需求文档拆解为可人工确认的原子需求点。
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    # 分析需求点与现有标准用例之间的覆盖关系。
    COVERAGE_ANALYSIS = "coverage_analysis"
    # 把用户开放目标规划成受控能力步骤；只负责规划，不直接执行工具。
    SUPERVISOR_PLANNING = "supervisor_planning"
    # 把产品人员的自然语言问题转换为受控只读 SQL，并解释查询结果。
    DATA_QUERY = "data_query"


class DataSourceDatabaseType(StrEnum):
    """智能数据查询当前支持的数据库方言。"""

    MYSQL = "MYSQL"
    POSTGRESQL = "POSTGRESQL"


class DataQueryExecutionStatus(StrEnum):
    """一次自然语言数据查询从创建到结束的状态。"""

    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class RequirementStatus(StrEnum):
    """需求从录入到确认的生命周期状态。"""

    # 草稿
    DRAFT = "DRAFT"
    # 提取
    EXTRACTING = "EXTRACTING"
    # 审核中
    REVIEWING = "REVIEWING"
    # 已确认
    CONFIRMED = "CONFIRMED"
    # 失败
    FAILED = "FAILED"
    # 已归档
    ARCHIVED = "ARCHIVED"


class RequirementExtractionTaskStatus(StrEnum):
    """一次 AI 需求拆解任务从排队到结束的执行状态。"""

    # API 已保存任务，等待 Celery Worker 领取。
    PENDING = "PENDING"
    # Worker 已领取任务，正在读取文档、调用模型或保存需求点。
    RUNNING = "RUNNING"
    # 需求点已经成功写入，等待测试人员校正和确认。
    COMPLETED = "COMPLETED"
    # 某一步执行失败，error_message 中保存脱敏后的失败原因。
    FAILED = "FAILED"
    # 任务在执行前或执行期间被人工取消。
    CANCELLED = "CANCELLED"


class RequirementExtractionStage(StrEnum):
    """需求拆解任务当前所处的业务阶段，供前端展示进度。"""

    QUEUED = "QUEUED"
    LOADING_DOCUMENT = "LOADING_DOCUMENT"
    CALLING_MODEL = "CALLING_MODEL"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    SAVING_ITEMS = "SAVING_ITEMS"
    FINISHED = "FINISHED"


class RequirementItemType(StrEnum):
    """原子需求点类型，对应需求拆解时需要识别的业务信息。"""

    FUNCTIONAL = "FUNCTIONAL"
    BUSINESS_RULE = "BUSINESS_RULE"
    NORMAL_FLOW = "NORMAL_FLOW"
    EXCEPTION_FLOW = "EXCEPTION_FLOW"
    BOUNDARY = "BOUNDARY"
    PERMISSION = "PERMISSION"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    COMPATIBILITY = "COMPATIBILITY"
    OTHER = "OTHER"


class TestAssetPriority(StrEnum):
    """需求点和测试用例共用的优先级。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TestCaseType(StrEnum):
    """测试用例覆盖的测试类型。"""

    FUNCTIONAL = "FUNCTIONAL"
    API = "API"
    UI = "UI"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    COMPATIBILITY = "COMPATIBILITY"
    REGRESSION = "REGRESSION"
    SMOKE = "SMOKE"
    OTHER = "OTHER"


class TestCaseStatus(StrEnum):
    """测试用例从草稿到发布的生命周期状态。"""

    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    DISABLED = "DISABLED"


class TestCaseSource(StrEnum):
    """测试用例的产生方式。"""

    MANUAL = "MANUAL"
    AI_GENERATED = "AI_GENERATED"
    IMPORTED = "IMPORTED"


class AutomationDefinitionStatus(StrEnum):
    """自动化测试定义从编辑到可执行的生命周期状态。"""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class AutomationDefinitionChangeAction(StrEnum):
    """自动化定义审计链中的变更动作。"""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"
    DELETED = "DELETED"


class AutomationHttpMethod(StrEnum):
    """受控接口测试定义允许使用的 HTTP（超文本传输协议）方法。"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class AutomationAssertionType(StrEnum):
    """执行器能够识别的有限断言类型；不允许定义任意代码断言。"""

    STATUS_CODE = "STATUS_CODE"
    JSON_PATH_EQUALS = "JSON_PATH_EQUALS"
    JSON_PATH_EXISTS = "JSON_PATH_EXISTS"
    HEADER_EQUALS = "HEADER_EQUALS"
    BODY_CONTAINS = "BODY_CONTAINS"
    RESPONSE_TIME_LE = "RESPONSE_TIME_LE"


class AutomationExtractorSource(StrEnum):
    """跨步骤提取变量时允许读取的响应位置。"""

    JSON_BODY = "JSON_BODY"
    HEADER = "HEADER"


class TestEnvironmentType(StrEnum):
    """测试环境用途；PRODUCTION 仅用于登记，自动化执行器禁止使用。"""

    LOCAL = "LOCAL"
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class AutomationExecutionStatus(StrEnum):
    """一次后台自动化执行任务的生命周期状态。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class AutomationStepStatus(StrEnum):
    """自动化报告中单个步骤的执行结果。"""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class NotificationChannelType(StrEnum):
    """平台能够安全管理和调用的通知渠道类型。

    WEBHOOK 是通用 HTTP（超文本传输协议）回调；WECHAT_WORK_BOT 和
    DINGTALK_BOT 分别表示企业微信、钉钉群机器人；SMTP 是简单邮件传输
    协议。使用固定枚举可以避免数据库中出现无法被发送器识别的任意类型。
    """

    WEBHOOK = "WEBHOOK"
    WECHAT_WORK_BOT = "WECHAT_WORK_BOT"
    DINGTALK_BOT = "DINGTALK_BOT"
    SMTP = "SMTP"


class RequirementCoverageType(StrEnum):
    """已有用例对某一原子需求点的覆盖程度。"""

    FULL = "FULL"
    PARTIAL = "PARTIAL"


class CaseGenerationTaskStatus(StrEnum):
    """一次用例生成任务的执行状态。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CaseReviewAction(StrEnum):
    """人工审核 AI 生成用例时可以执行的动作。"""

    SUBMIT = "SUBMIT"
    ACCEPT = "ACCEPT"
    MODIFY = "MODIFY"
    REJECT = "REJECT"
    DUPLICATE = "DUPLICATE"
    PUBLISH = "PUBLISH"
    DISABLE = "DISABLE"


class AIUsageStatus(StrEnum):
    """一次 AI 调用的最终执行状态。"""

    # 模型调用完成，并取得了可用结果。
    SUCCESS = "success"
    # 模型调用发生异常；日志中只保存脱敏后的异常摘要。
    FAILED = "failed"


class KnowledgeChatSessionStatus(StrEnum):
    """知识问答会话状态。"""

    # 正常参与问答和历史加载。
    ACTIVE = "ACTIVE"
    # 用户主动归档；保留历史，但不再作为默认当前会话。
    ARCHIVED = "ARCHIVED"


class KnowledgeChatMessageRole(StrEnum):
    """知识问答消息发送方。"""

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class KnowledgeChatMessageStatus(StrEnum):
    """消息处理状态，用于区分生成中、成功和失败。"""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class KnowledgeChatMemoryStatus(StrEnum):
    """会话摘要生成及向量化状态。"""

    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class KnowledgeChatStreamEventType(StrEnum):
    # 告诉前端正在执行哪个阶段。
    STATUS = "STATUS"
    # 模型新生成的一小段文字。
    DELTA = "DELTA"
    # 回答使用的引用资料。
    CITATIONS = "CITATIONS"
    # 整个流程完成，携带数据库真实消息。
    DONE = "DONE"
    # 生成失败。
    ERROR = "ERROR"


class KnowledgeChatStreamStage(StrEnum):
    SAVING = "SAVING"
    REWRITING = "REWRITING"
    RETRIEVING = "RETRIEVING"
    RERANKING = "RERANKING"
    GENERATING = "GENERATING"
    SAVING_RESULT = "SAVING_RESULT"


# 各内置 Prompt 运行时必须提供的变量。
PROMPT_REQUIRED_VARIABLES: dict[str, frozenset[str]] = {
    "rag_answer": frozenset({"context", "memory", "question"}),
    "query_rewrite": frozenset({"conversation", "question"}),
    "document_summary": frozenset({"content"}),
    "knowledge_chat_memory_summary": frozenset({"conversation"}),
    "requirement_analysis": frozenset({"requirement_text", "validation_feedback", "output_schema"}),
    "coverage_analysis": frozenset(
        {
            "requirements_json",
            "candidate_cases_json",
            "output_schema",
            "validation_feedback",
        }
    ),
    "test_case_generation": frozenset(
        {
            "coverage_gaps_json",
            "reference_cases_json",
            "output_schema",
            "validation_feedback",
        }
    ),
    "supervisor_planning": frozenset(
        {
            "goal",
            "business_context_json",
            "available_capabilities_json",
            "output_schema",
            "validation_feedback",
        }
    ),
    "data_query_sql": frozenset(
        {
            "database_type",
            "database_name",
            "schema_context",
            "question",
            "validation_feedback",
            "output_schema",
        }
    ),
    "data_query_summary": frozenset(
        {
            "question",
            "sql",
            "result_json",
            "output_schema",
        }
    ),
}

# 程序直接依赖的内置 Prompt 编码，不允许物理删除。
BUILT_IN_PROMPT_CODES: frozenset[str] = frozenset(PROMPT_REQUIRED_VARIABLES)
