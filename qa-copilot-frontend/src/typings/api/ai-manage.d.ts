declare namespace Api {
  /** AI provider and model management APIs. */
  namespace AIManage {
    type ProviderType = 'openai_responses' | 'openai_compatible';

    type Provider = {
      id: number;
      name: string;
      providerType: ProviderType;
      baseUrl: string | null;
      customHeaders: Record<string, string>;
      timeoutSeconds: number;
      maxRetries: number;
      enabled: boolean;
      apiKeyMasked: string;
      createdAt: string;
      updatedAt: string;
    };

    type ProviderCreateParams = {
      name: string;
      providerType: ProviderType;
      baseUrl: string | null;
      apiKey: string;
      customHeaders: Record<string, string>;
      timeoutSeconds: number;
      maxRetries: number;
      enabled: boolean;
    };

    type ProviderUpdateParams = Partial<ProviderCreateParams>;

    type Model = {
      id: number;
      providerId: number;
      providerName: string;
      name: string;
      modelId: string;
      reasoningEffort: string | null;
      contextWindowTokens: number;
      maxOutputTokens: number;
      enabled: boolean;
      isDefault: boolean;
      taskTypes: string[];
      createdAt: string;
      updatedAt: string;
    };

    type ModelCreateParams = {
      providerId: number;
      name: string;
      modelId: string;
      reasoningEffort: string | null;
      contextWindowTokens: number;
      maxOutputTokens: number;
      enabled: boolean;
      isDefault: boolean;
      taskTypes: string[];
    };

    type ModelUpdateParams = Partial<Omit<ModelCreateParams, 'providerId'>>;

    type ModelConnectionTestParams = {
      modelId: number;
      prompt: string;
    };

    type ModelConnectionTestResult = {
      success: boolean;
      content: string;
      latencyMs: number;
    };

    /** Prompt 列表只返回摘要信息，避免分页接口携带大段模板正文。 */
    type PromptTemplateSummary = {
      id: number;
      code: string;
      name: string;
      description: string;
      enabled: boolean;
      createdAt: string;
      updatedAt: string;
    };

    /** Prompt 详情在摘要基础上补充系统提示词和用户提示词。 */
    type PromptTemplate = PromptTemplateSummary & {
      systemPrompt: string;
      userPrompt: string;
    };

    type PromptTemplateSearchParams = {
      current: number;
      size: number;
      keyword: string;
      enabled?: boolean;
    };

    type PromptTemplateCreateParams = {
      code: string;
      name: string;
      description: string;
      systemPrompt: string;
      userPrompt: string;
      enabled: boolean;
    };

    /** 业务编码创建后不可修改，其余字段支持部分更新。 */
    type PromptTemplateUpdateParams = Partial<Omit<PromptTemplateCreateParams, 'code'>>;

    type PromptTemplateList = Common.PaginatingQueryRecord<PromptTemplateSummary>;
    type PromptTemplatePreview = {
      code: string;
      variables: string[];
      renderedSystemPrompt: string;
      renderedUserPrompt: string;
    };

    type UsageStatus = 'success' | 'failed';

    /** 调用日志列表中的一条记录。 */
    type UsageLog = {
      id: number;
      requestId: string | null;
      taskId: string | null;
      userId: number | null;
      userName: string | null;
      projectId: number | null;
      projectName: string | null;
      providerId: number | null;
      providerName: string;
      modelId: number | null;
      modelName: string;
      taskType: string;
      status: UsageStatus;
      inputTokens: number;
      outputTokens: number;
      totalTokens: number;
      latencyMs: number;
      createdAt: string;
    };

    /** 详情在列表字段上补充检索命中数和脱敏后的失败原因。 */
    type UsageLogDetail = UsageLog & {
      retrievalHitCount: number;
      errorMessage: string | null;
    };

    /** 列表和统计接口共用的筛选条件。 */
    type UsageLogFilterParams = {
      providerId?: number;
      modelId?: number;
      userId?: number;
      projectId?: number;
      taskType?: string;
      status?: UsageStatus;
      requestId?: string;
      taskId?: string;
      startTime?: string;
      endTime?: string;
    };

    type UsageLogSearchParams = UsageLogFilterParams & {
      current: number;
      size: number;
    };

    type UsageLogList = Common.PaginatingQueryRecord<UsageLog>;

    /** 当前筛选范围内的次数、Token 和耗时统计。 */
    type UsageLogStatistics = {
      totalCalls: number;
      successCalls: number;
      failedCalls: number;
      successRate: number;
      inputTokens: number;
      outputTokens: number;
      totalTokens: number;
      averageLatencyMs: number;
      maxLatencyMs: number;
      p95LatencyMs: number;
    };

    type NotificationChannelType = 'WEBHOOK' | 'WECHAT_WORK_BOT' | 'DINGTALK_BOT' | 'SMTP';

    type NotificationChannelConfig = {
      timeoutSeconds: number;
      host?: string;
      port?: number;
      security?: 'NONE' | 'STARTTLS' | 'SSL';
      username?: string;
      fromEmail?: string;
      recipients?: string[];
      subjectPrefix?: string;
    };

    /** 通知渠道查询结果不包含 Webhook 地址、令牌或邮箱密码。 */
    type NotificationChannel = {
      id: number;
      name: string;
      channelType: NotificationChannelType;
      config: NotificationChannelConfig;
      secretConfigured: boolean;
      enabled: boolean;
      importanceThreshold: number;
      breakingOnly: boolean;
      createdAt: string;
      updatedAt: string;
    };

    type NotificationChannelCreateParams = {
      name: string;
      channelType: NotificationChannelType;
      config: NotificationChannelConfig;
      secret: string;
      enabled: boolean;
      importanceThreshold: number;
      breakingOnly: boolean;
    };

    type NotificationChannelUpdateParams = Partial<NotificationChannelCreateParams>;

    type NotificationChannelTestResult = {
      success: boolean;
      message: string;
      latencyMs: number;
    };
  }
}
