import { request } from '../request';

/** Get configured AI providers. */
export function fetchGetAIProviderList() {
  return request<Api.AIManage.Provider[]>({
    url: '/ai_provider/list',
    method: 'get'
  });
}

/** Create an AI provider. */
export function fetchCreateAIProvider(data: Api.AIManage.ProviderCreateParams) {
  return request<Api.AIManage.Provider>({
    url: '/ai_provider/create',
    method: 'post',
    data
  });
}

/** Update an AI provider. */
export function fetchUpdateAIProvider(providerId: number, data: Api.AIManage.ProviderUpdateParams) {
  return request<Api.AIManage.Provider>({
    url: `/ai_provider/update/${providerId}`,
    method: 'put',
    data
  });
}

/** Delete an AI provider. */
export function fetchDeleteAIProvider(providerId: number) {
  return request<null>({
    url: `/ai_provider/providers/${providerId}`,
    method: 'delete'
  });
}

/** Get configured AI models. */
export function fetchGetAIModelList() {
  return request<Api.AIManage.Model[]>({
    url: '/ai-model/list',
    method: 'get'
  });
}

/** Create an AI model. */
export function fetchCreateAIModel(data: Api.AIManage.ModelCreateParams) {
  return request<Api.AIManage.Model>({
    url: '/ai-model/models',
    method: 'post',
    data
  });
}

/** Update an AI model. */
export function fetchUpdateAIModel(modelId: number, data: Api.AIManage.ModelUpdateParams) {
  return request<Api.AIManage.Model>({
    url: `/ai-model/models/${modelId}`,
    method: 'put',
    data
  });
}

/** Delete an AI model. */
export function fetchDeleteAIModel(modelId: number) {
  return request<null>({
    url: `/ai-model/models/${modelId}`,
    method: 'delete'
  });
}

/** Test an AI model connection. */
export function fetchTestAIModelConnection(data: Api.AIManage.ModelConnectionTestParams) {
  return request<Api.AIManage.ModelConnectionTestResult>({
    url: '/ai-model/test',
    method: 'post',
    data
  });
}

/** 分页查询 Prompt 模板摘要。 */
export function fetchGetPromptTemplateList(params: Api.AIManage.PromptTemplateSearchParams) {
  return request<Api.AIManage.PromptTemplateList>({
    url: '/prompt_templates',
    method: 'get',
    params
  });
}

/** 查询 Prompt 模板详情。 */
export function fetchGetPromptTemplate(promptId: number) {
  return request<Api.AIManage.PromptTemplate>({
    url: `/prompt_templates/${promptId}`,
    method: 'get'
  });
}

/** 创建 Prompt 模板。 */
export function fetchCreatePromptTemplate(data: Api.AIManage.PromptTemplateCreateParams) {
  return request<Api.AIManage.PromptTemplate>({
    url: '/prompt_templates',
    method: 'post',
    data
  });
}

/** 更新 Prompt 模板，业务编码保持不变。 */
export function fetchUpdatePromptTemplate(promptId: number, data: Api.AIManage.PromptTemplateUpdateParams) {
  return request<Api.AIManage.PromptTemplate>({
    url: `/prompt_templates/${promptId}`,
    method: 'put',
    data
  });
}

/** 删除自定义 Prompt 模板；系统内置模板由后端拒绝删除。 */
export function fetchDeletePromptTemplate(promptId: number) {
  return request<null>({
    url: `/prompt_templates/${promptId}`,
    method: 'delete'
  });
}

/** 预览当前尚未保存的 Prompt 编辑内容。 */
export function fetchPreviewPromptTemplate(data: {
  code: string;
  systemPrompt: string;
  userPrompt: string;
  variables: Record<string, string>;
}) {
  return request<Api.AIManage.PromptTemplatePreview>({
    url: '/prompt_templates/preview/render',
    method: 'post',
    data
  });
}

/** 分页查询 AI 调用日志。 */
export function fetchGetAIUsageLogList(params: Api.AIManage.UsageLogSearchParams) {
  return request<Api.AIManage.UsageLogList>({
    url: '/ai_usage_logs/list',
    method: 'get',
    params
  });
}

/** 查询当前筛选范围内的调用次数、Token 和耗时统计。 */
export function fetchGetAIUsageLogStatistics(params: Api.AIManage.UsageLogFilterParams) {
  return request<Api.AIManage.UsageLogStatistics>({
    url: '/ai_usage_logs/statistics',
    method: 'get',
    params
  });
}

/** 查询一次 AI 调用的审计详情。 */
export function fetchGetAIUsageLogDetail(logId: number) {
  return request<Api.AIManage.UsageLogDetail>({
    url: `/ai_usage_logs/detail/${logId}`,
    method: 'get'
  });
}

/** 查询所有通知渠道；后端只返回密钥是否已配置。 */
export function fetchGetNotificationChannelList() {
  return request<Api.AIManage.NotificationChannel[]>({
    url: '/notification-channels',
    method: 'get'
  });
}

/** 创建通知渠道，secret 会由后端加密保存。 */
export function fetchCreateNotificationChannel(data: Api.AIManage.NotificationChannelCreateParams) {
  return request<Api.AIManage.NotificationChannel>({
    url: '/notification-channels',
    method: 'post',
    data
  });
}

/** 部分更新通知渠道；不传 secret 表示保留原密钥。 */
export function fetchUpdateNotificationChannel(channelId: number, data: Api.AIManage.NotificationChannelUpdateParams) {
  return request<Api.AIManage.NotificationChannel>({
    url: `/notification-channels/${channelId}`,
    method: 'put',
    data
  });
}

/** 删除通知渠道。 */
export function fetchDeleteNotificationChannel(channelId: number) {
  return request<null>({
    url: `/notification-channels/${channelId}`,
    method: 'delete'
  });
}

/** 使用已保存配置发送一条真实测试通知。 */
export function fetchTestNotificationChannel(channelId: number) {
  return request<Api.AIManage.NotificationChannelTestResult>({
    url: `/notification-channels/${channelId}/test`,
    method: 'post'
  });
}
