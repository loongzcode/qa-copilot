declare namespace Api {
  /** Supervisor Agent（监督编排智能体）规划运行接口。 */
  namespace Supervisor {
    type InvocationSource = 'SUPERVISOR' | 'MCP';
    type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
    type StepDecision = 'READY' | 'BLOCKED_APPROVAL' | 'REJECTED';
    type RunStatus =
      | 'PLANNING'
      | 'PLAN_REJECTED'
      | 'READY'
      | 'WAITING_APPROVAL'
      | 'RUNNING'
      | 'SUCCEEDED'
      | 'FAILED'
      | 'CANCELLED';
    type StepStatus =
      | 'PROPOSED'
      | 'REJECTED'
      | 'READY'
      | 'WAITING_APPROVAL'
      | 'RUNNING'
      | 'SUCCEEDED'
      | 'FAILED'
      | 'SKIPPED'
      | 'CANCELLED';

    /** 创建计划时允许前端补充的结构化业务对象编号。 */
    type BusinessContext = {
      requirementId?: number;
      knowledgeBaseId?: number;
      moduleId?: number;
    };

    type CreateRunParams = {
      goal: string;
      businessContext: BusinessContext;
      sessionId?: number;
    };

    type Session = {
      id: number;
      projectId: number;
      title: string;
      createdBy: number | null;
      createdAt: string;
      updatedAt: string;
    };

    type ApprovalParams = {
      decision: 'APPROVED' | 'REJECTED';
      comment: string;
    };

    type RunSearchParams = {
      current: number;
      size: number;
      status?: RunStatus;
      sessionId?: number;
    };

    type PlanStep = {
      id: number;
      sessionId: number | null;
      stepNo: number;
      stepKey: string;
      capabilityCode: string;
      purpose: string;
      argumentsSnapshot: Record<string, unknown>;
      dependsOn: string[];
      requiredPermission: string;
      riskLevel: RiskLevel;
      decision: StepDecision;
      requiresHumanApproval: boolean;
      status: StepStatus;
      toolTaskId: number | null;
      resultSnapshot: Record<string, unknown>;
      errorMessage: string | null;
      startedAt: string | null;
      finishedAt: string | null;
      approvalDecidedBy: number | null;
      approvalDecision: 'APPROVED' | 'REJECTED' | null;
      approvalComment: string | null;
      approvalDecidedAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type Run = {
      id: number;
      projectId: number;
      goal: string;
      invocationSource: InvocationSource;
      status: RunStatus;
      currentStepNo: number;
      planVersion: number;
      modelId: number | null;
      requestedBy: number | null;
      errorMessage: string | null;
      startedAt: string | null;
      finishedAt: string | null;
      executionHeartbeatAt: string | null;
      executionRecoveryCount: number;
      createdAt: string;
      updatedAt: string;
    };

    type RunDetail = Run & {
      permissionSnapshot: string[];
      contextSnapshot: Record<string, unknown>;
      resultSummary: Record<string, unknown>;
      steps: PlanStep[];
    };

    type RunList = Common.PaginatingQueryRecord<Run>;
  }
}
