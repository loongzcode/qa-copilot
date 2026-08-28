declare namespace Api {
  /** 受控测试工具、外部连接、文件模板、审批和执行任务。 */
  namespace ToolManage {
    type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';
    type ConnectionType = 'MYSQL' | 'NACOS' | 'BUSINESS_API' | 'DEFECT_PLATFORM';
    type TaskType =
      | 'FILE_GENERATE'
      | 'FILE_VALIDATE'
      | 'MYSQL_COMPARE'
      | 'MYSQL_SYNC'
      | 'NACOS_COMPARE'
      | 'NACOS_SYNC'
      | 'DEFECT_SYNC'
      | 'UI_AUTOMATION';
    type TaskStatus =
      | 'DRAFT'
      | 'PREVIEWED'
      | 'PENDING_APPROVAL'
      | 'APPROVED'
      | 'REJECTED'
      | 'RUNNING'
      | 'SUCCEEDED'
      | 'FAILED'
      | 'ROLLED_BACK'
      | 'CANCELLED';
    type FileFormat = 'CSV' | 'EXCEL' | 'FIXED_WIDTH_TXT' | 'DELIMITED_TXT' | 'JSON' | 'XML';

    type ToolDefinition = {
      id: number;
      code: string;
      name: string;
      description: string;
      riskLevel: RiskLevel;
      requiredPermission: string;
      enabled: boolean;
    };
    type Connection = {
      id: number;
      projectId: number;
      name: string;
      connectionType: ConnectionType;
      config: Record<string, any>;
      credentialsConfigured: boolean;
      enabled: boolean;
      createdAt: string;
      updatedAt: string;
    };
    type ConnectionCreateParams = {
      name: string;
      connectionType: ConnectionType;
      config: Record<string, any>;
      credentials: Record<string, string>;
      enabled: boolean;
    };
    type ConnectionUpdateParams = Omit<ConnectionCreateParams, 'connectionType' | 'credentials'> & {
      credentials?: Record<string, string>;
    };

    type TemplateField = {
      name: string;
      sourceField: string;
      dataType: 'STRING' | 'INTEGER' | 'DECIMAL' | 'DATE' | 'DATETIME' | 'BOOLEAN';
      required: boolean;
      length?: number | null;
      precision?: number | null;
      format?: string | null;
      padding?: 'LEFT' | 'RIGHT' | null;
      paddingChar: string;
      mapping: Record<string, string>;
      defaultValue?: any;
    };
    type FileTemplate = {
      id: number;
      projectId: number;
      name: string;
      fileFormat: FileFormat;
      encoding: 'UTF-8' | 'GBK';
      delimiter: string | null;
      fields: TemplateField[];
      headerConfig: Record<string, any>;
      trailerConfig: Record<string, any>;
      enabled: boolean;
      createdAt: string;
      updatedAt: string;
    };
    type FileTemplateParams = Omit<FileTemplate, 'id' | 'projectId' | 'createdAt' | 'updatedAt'>;

    type Approval = {
      id: number;
      requesterId: number | null;
      approverId: number | null;
      decision: 'APPROVED' | 'REJECTED';
      comment: string;
      previewHash: string;
      createdAt: string;
    };
    type Log = {
      id: number;
      stage: string;
      level: string;
      message: string;
      details: Record<string, any>;
      createdAt: string;
    };
    type Artifact = {
      id: number;
      artifactType: string;
      name: string;
      contentType: string;
      sizeBytes: number;
      sha256: string;
      createdAt: string;
    };
    type Task = {
      id: number;
      projectId: number;
      toolId: number;
      toolCode: string;
      toolName: string;
      taskType: TaskType;
      title: string;
      riskLevel: RiskLevel;
      status: TaskStatus;
      requestedBy: number | null;
      inputData: Record<string, any>;
      previewData: Record<string, any> | null;
      previewHash: string | null;
      resultData: Record<string, any> | null;
      rollbackData: Record<string, any> | null;
      errorMessage: string | null;
      startedAt: string | null;
      finishedAt: string | null;
      createdAt: string;
      updatedAt: string;
      approvals: Approval[];
      logs: Log[];
      artifacts: Artifact[];
    };
    type TaskCreateParams = { toolCode: string; taskType: TaskType; title: string; inputData: Record<string, any> };
    type TaskSearchParams = { current: number; size: number; status?: TaskStatus; taskType?: TaskType };
    type TaskList = Common.PaginatingQueryRecord<Task>;
  }
}
