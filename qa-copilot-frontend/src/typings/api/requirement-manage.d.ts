declare namespace Api {
  /** 需求分析、覆盖分析和测试用例管理接口。 */
  namespace RequirementManage {
    type RequirementStatus = 'DRAFT' | 'EXTRACTING' | 'REVIEWING' | 'CONFIRMED' | 'FAILED' | 'ARCHIVED';
    type RequirementExtractionTaskStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
    type RequirementExtractionStage =
      | 'QUEUED'
      | 'LOADING_DOCUMENT'
      | 'CALLING_MODEL'
      | 'VALIDATING_OUTPUT'
      | 'SAVING_ITEMS'
      | 'FINISHED';
    type RequirementItemType =
      | 'FUNCTIONAL'
      | 'BUSINESS_RULE'
      | 'NORMAL_FLOW'
      | 'EXCEPTION_FLOW'
      | 'BOUNDARY'
      | 'PERMISSION'
      | 'PERFORMANCE'
      | 'SECURITY'
      | 'COMPATIBILITY'
      | 'OTHER';
    type Priority = 'P0' | 'P1' | 'P2' | 'P3';
    type TestCaseType =
      | 'FUNCTIONAL'
      | 'API'
      | 'UI'
      | 'PERFORMANCE'
      | 'SECURITY'
      | 'COMPATIBILITY'
      | 'REGRESSION'
      | 'SMOKE'
      | 'OTHER';
    type TestCaseStatus = 'DRAFT' | 'REVIEWING' | 'APPROVED' | 'REJECTED' | 'PUBLISHED' | 'DISABLED';
    type TestCaseSource = 'MANUAL' | 'AI_GENERATED' | 'IMPORTED';
    type CoverageType = 'FULL' | 'PARTIAL';
    type GenerationTaskStatus = 'PENDING' | 'RUNNING' | 'WAITING_REVIEW' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
    type ReviewAction = 'SUBMIT' | 'ACCEPT' | 'MODIFY' | 'REJECT' | 'DUPLICATE' | 'PUBLISH' | 'DISABLE';
    type QualityDeliveryStage =
      | 'START_REQUIREMENT_AGENT'
      | 'REQUIREMENT_AGENT_RUNNING'
      | 'REQUIREMENT_AGENT_FAILED'
      | 'HUMAN_REQUIREMENT_REVIEW'
      | 'START_CASE_AGENT'
      | 'CASE_AGENT_RUNNING'
      | 'CASE_AGENT_FAILED'
      | 'HUMAN_CASE_REVIEW'
      | 'IMPROVE_AUTOMATION_DATA'
      | 'READY_FOR_AUTOMATION';

    /** 需求拆解、用例生成与自动化准备的统一交付状态。 */
    type QualityDeliveryStatus = {
      stage: QualityDeliveryStage;
      currentAgent: string | null;
      nextAction: string;
      blockers: string[];
      requirementItemCount: number;
      confirmedItemCount: number;
      reviewCaseCount: number;
      publishedCaseCount: number;
      automatablePublishedCaseCount: number;
    };

    type Requirement = {
      id: number;
      projectId: number;
      moduleId: number | null;
      moduleName: string | null;
      documentId: number | null;
      documentTitle: string | null;
      documentParseStatus: Api.KnowledgeManage.KnowledgeDocumentParseStatus | null;
      title: string;
      version: string;
      status: RequirementStatus;
      sourceUrl: string | null;
      summary: string;
      metadata?: Record<string, unknown>;
      createdBy: number | null;
      createdByName: string | null;
      itemCount: number;
      confirmedItemCount: number;
      createdAt: string;
      updatedAt: string;
    };

    type RequirementItem = {
      id: number;
      requirementId: number;
      parentId: number | null;
      itemCode: string | null;
      title: string;
      description: string;
      itemType: RequirementItemType;
      priority: Priority;
      acceptanceCriteria: string;
      sourceLocator: Record<string, unknown>;
      aiGenerated: boolean;
      confirmed: boolean;
      orderNo: number;
      createdAt: string;
      updatedAt: string;
      children?: RequirementItem[];
    };

    type RequirementDetail = Requirement & {
      items: RequirementItem[];
    };

    /** 一次后台需求拆解任务的进度、结果快照和审计信息。 */
    type RequirementExtractionTask = {
      id: number;
      projectId: number;
      requirementId: number;
      celeryTaskId: string;
      modelId: number | null;
      promptTemplateId: number | null;
      status: RequirementExtractionTaskStatus;
      progress: number;
      currentStage: RequirementExtractionStage;
      inputSnapshot: Record<string, unknown>;
      outputSnapshot: Record<string, unknown>;
      errorMessage: string | null;
      requestedBy: number | null;
      requestedByName: string | null;
      startedAt: string | null;
      finishedAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type RequirementExtractionSubmitParams = {
      replaceUnconfirmedAiItems: boolean;
    };

    type RequirementSearchParams = {
      current: number;
      size: number;
      keyword: string;
      status?: RequirementStatus;
    };

    type RequirementList = Common.PaginatingQueryRecord<Requirement>;

    type RequirementCreateParams = {
      moduleId: number | null;
      documentId: number | null;
      title: string;
      version: string;
      sourceUrl: string | null;
      summary?: string;
      metadata?: Record<string, unknown>;
    };

    type RequirementUpdateParams = Partial<RequirementCreateParams>;

    /** 新建或编辑需求时，直接上传来源文件所需的 multipart 业务参数。 */
    type RequirementSourceDocumentUploadParams = {
      knowledgeBaseId: number;
      file: File;
      title?: string;
      moduleId?: number;
      metadata?: Record<string, unknown>;
    };

    type RequirementItemCreateParams = {
      parentId: number | null;
      itemCode: string | null;
      title: string;
      description: string;
      itemType: RequirementItemType;
      priority: Priority;
      acceptanceCriteria: string;
      sourceLocator: Record<string, unknown>;
      orderNo?: number;
    };

    type RequirementItemUpdateParams = Partial<RequirementItemCreateParams>;

    type RequirementFormOptions = {
      modules: Array<{ id: number; name: string }>;
      knowledgeBases: Array<{ id: number; name: string }>;
      documents: Array<{ id: number; title: string; version: number }>;
    };

    type TestCaseStep = {
      id: number;
      testCaseId: number;
      stepNo: number;
      action: string;
      testData: unknown | null;
      expectedResult: string;
      createdAt: string;
      updatedAt: string;
    };

    type TestCase = {
      id: number;
      projectId: number;
      moduleId: number | null;
      moduleName: string | null;
      caseCode: string | null;
      title: string;
      caseType: TestCaseType;
      priority: Priority;
      preconditions: string;
      expectedSummary: string;
      status: TestCaseStatus;
      source: TestCaseSource;
      automatable: boolean;
      version: number;
      metadata?: Record<string, unknown>;
      createdBy: number | null;
      createdByName: string | null;
      updatedBy: number | null;
      steps: TestCaseStep[];
      requirementItemIds?: number[];
      createdAt: string;
      updatedAt: string;
    };

    type TestCaseSearchParams = {
      current: number;
      size: number;
      keyword: string;
      moduleId?: number;
      status?: TestCaseStatus;
      source?: TestCaseSource;
    };

    type TestCaseList = Common.PaginatingQueryRecord<TestCase>;

    type TestCaseCreateParams = {
      moduleId: number | null;
      caseCode: string | null;
      title: string;
      caseType: TestCaseType;
      priority: Priority;
      preconditions: string;
      expectedSummary: string;
      automatable: boolean;
      version: number;
      metadata?: Record<string, unknown>;
      steps: Array<Omit<TestCaseStep, 'id' | 'testCaseId' | 'createdAt' | 'updatedAt'>>;
      requirementItemIds: number[];
    };

    type TestCaseRequirementItemOption = {
      id: number;
      requirementId: number;
      requirementTitle: string;
      itemCode: string | null;
      title: string;
      itemType: RequirementItemType;
      priority: Priority;
    };

    type CoverageLink = {
      requirementItemId: number;
      testCaseId: number;
      testCaseCode: string;
      testCaseTitle: string;
      coverageType: CoverageType;
      confidence: number | null;
      evidence: Record<string, unknown>;
    };

    type CoverageRow = {
      requirementItem: RequirementItem;
      coverageStatus: CoverageType | 'UNCOVERED';
      links: CoverageLink[];
    };

    type CoverageMatrix = {
      requirementId: number;
      totalItems: number;
      fullCount: number;
      partialCount: number;
      uncoveredCount: number;
      rows: CoverageRow[];
    };

    type GenerationTask = {
      id: number;
      projectId: number;
      requirementId: number;
      requirementTitle?: string;
      modelId: number | null;
      promptTemplateId: number | null;
      status: GenerationTaskStatus;
      inputSnapshot: Record<string, unknown>;
      outputSnapshot: Record<string, unknown>;
      retrievalSnapshot: Record<string, unknown>;
      progress: number;
      currentStage: string | null;
      errorMessage: string | null;
      requestedBy: number | null;
      startedAt: string | null;
      finishedAt: string | null;
      draftCases?: TestCase[];
      createdAt: string;
      updatedAt: string;
    };

    type GenerationTaskSearchParams = {
      current: number;
      size: number;
      requirementId?: number;
      status?: GenerationTaskStatus;
    };

    type GenerationTaskList = Common.PaginatingQueryRecord<GenerationTask>;

    type CaseReviewParams = {
      action: ReviewAction;
      comment: string;
    };

    /** 一次批量审核请求；整批成功或整批回滚。 */
    type CaseBatchReviewParams = CaseReviewParams & {
      testCaseIds: number[];
    };
  }
}
