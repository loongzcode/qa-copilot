declare namespace Api {
  /** 受控接口自动化定义管理接口。 */
  namespace AutomationManage {
    type DefinitionStatus = 'DRAFT' | 'APPROVED' | 'RETIRED';
    type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';
    type AssertionType =
      | 'STATUS_CODE'
      | 'JSON_PATH_EQUALS'
      | 'JSON_PATH_EXISTS'
      | 'HEADER_EQUALS'
      | 'BODY_CONTAINS'
      | 'RESPONSE_TIME_LE';
    type ExtractorSource = 'JSON_BODY' | 'HEADER';

    type RequestDefinition = {
      method: HttpMethod;
      path: string;
      headers: Record<string, unknown>;
      query: Record<string, unknown>;
      jsonBody?: unknown;
      formBody?: Record<string, unknown>;
      timeoutSeconds: number;
    };

    type AssertionDefinition = {
      type: AssertionType;
      expression?: string | null;
      expected?: unknown;
    };

    type ExtractorDefinition = {
      name: string;
      source: ExtractorSource;
      expression: string;
    };

    type StepDefinition = {
      name: string;
      request: RequestDefinition;
      assertions: AssertionDefinition[];
      extractors: ExtractorDefinition[];
    };

    type DefinitionSpec = {
      schemaVersion: '1.0';
      steps: StepDefinition[];
    };

    type Definition = {
      id: number;
      projectId: number;
      testCaseId: number;
      testCaseTitle: string;
      name: string;
      version: number;
      status: DefinitionStatus;
      schemaVersion: string;
      sourceCaseVersion: number;
      definition: DefinitionSpec;
      definitionHash: string;
      createdBy: number | null;
      createdByName: string | null;
      approvedBy: number | null;
      approvedByName: string | null;
      approvedAt: string | null;
      retiredAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type DefinitionSearchParams = {
      current: number;
      size: number;
      keyword: string;
      status?: DefinitionStatus;
    };

    type DefinitionList = Common.PaginatingQueryRecord<Definition>;
    type DefinitionUpdateParams = { name: string; definition: DefinitionSpec };
    type DefinitionChangeAction = 'CREATED' | 'UPDATED' | 'APPROVED' | 'RETIRED' | 'DELETED';
    type DefinitionChange = {
      id: number;
      definitionId: number;
      version: number;
      action: DefinitionChangeAction;
      beforeSnapshot: Record<string, unknown> | null;
      afterSnapshot: Record<string, unknown> | null;
      changedBy: number | null;
      changedByName: string | null;
      createdAt: string;
    };

    /** 后台执行任务状态；CANCEL_REQUESTED 表示 Worker 正在终止子进程。 */
    type ExecutionStatus = 'PENDING' | 'RUNNING' | 'CANCEL_REQUESTED' | 'PASSED' | 'FAILED' | 'TIMED_OUT' | 'CANCELLED';

    type ExecutionSummary = {
      success?: boolean;
      stepCount?: number;
      passedSteps?: number;
      failedSteps?: number;
      skippedSteps?: number;
      failedStep?: number | null;
      message?: string;
      durationMs?: number;
    };

    type ExecutionTask = {
      id: number;
      projectId: number;
      definitionId: number;
      definitionName: string;
      definitionVersion: number;
      environmentId: number;
      environmentName: string;
      status: ExecutionStatus;
      progress: number;
      currentStage: string;
      timeoutSeconds: number;
      celeryTaskId: string | null;
      resultSummary: ExecutionSummary;
      errorMessage: string | null;
      requestedBy: number | null;
      requestedByName: string | null;
      startedAt: string | null;
      finishedAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type ExecutionTaskList = Common.PaginatingQueryRecord<ExecutionTask>;
    type ExecutionSearchParams = {
      current: number;
      size: number;
      status?: ExecutionStatus;
    };
    type ExecutionCreateParams = {
      definitionId: number;
      environmentId: number;
      timeoutSeconds: number;
    };

    type StepStatus = 'PASSED' | 'FAILED' | 'SKIPPED';
    type StepRequestSummary = {
      queryKeys: string[];
      headerNames: string[];
      bodyType: 'NONE' | 'JSON' | 'FORM';
      bodyFieldNames: string[];
    };
    type StepResponseSummary = {
      statusCode?: number;
      contentType?: string;
      bodySizeBytes?: number;
    };
    type StepAssertionResult = {
      type: AssertionType;
      expression?: string | null;
      expected?: unknown;
      actual?: unknown;
      passed: boolean;
    };
    type ExecutionStepResult = {
      id: number;
      stepNo: number;
      name: string;
      status: StepStatus;
      method: HttpMethod;
      path: string;
      statusCode: number | null;
      durationMs: number | null;
      requestSummary: StepRequestSummary;
      responseSummary: StepResponseSummary;
      assertions: StepAssertionResult[];
      errorMessage: string | null;
    };
    type ExecutionReport = {
      task: ExecutionTask;
      steps: ExecutionStepResult[];
    };

    type Schedule = {
      id: number;
      projectId: number;
      name: string;
      definitionId: number;
      definitionName: string;
      environmentId: number;
      environmentName: string;
      cronExpression: string;
      timezone: string;
      timeoutSeconds: number;
      enabled: boolean;
      nextRunAt: string;
      lastRunAt: string | null;
      createdAt: string;
      updatedAt: string;
    };
    type ScheduleParams = {
      name: string;
      definitionId: number;
      environmentId: number;
      cronExpression: string;
      timezone: string;
      timeoutSeconds: number;
      enabled: boolean;
    };
  }
}
