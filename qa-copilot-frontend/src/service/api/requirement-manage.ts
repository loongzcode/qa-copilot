import { request } from '../request';

/** 分页查询当前用户有权访问的项目需求。 */
export function fetchGetRequirementList(projectId: number, params: Api.RequirementManage.RequirementSearchParams) {
  return request<Api.RequirementManage.RequirementList>({
    url: `/requirements/${projectId}`,
    method: 'get',
    params
  });
}

/** 查询需求详情及其原子需求点。 */
export function fetchGetRequirementDetail(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.RequirementDetail>({
    url: `/requirements/${projectId}/${requirementId}`,
    method: 'get'
  });
}

/** 查询需求从 AI 拆解到自动化执行之间所处的交付阶段。 */
export function fetchGetQualityDeliveryStatus(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.QualityDeliveryStatus>({
    url: `/quality-delivery/${projectId}/requirements/${requirementId}/status`,
    method: 'get'
  });
}

/** 查询创建和编辑需求需要的模块、知识库和已有需求来源文档选项。 */
export function fetchGetRequirementFormOptions(projectId: number) {
  return request<Api.RequirementManage.RequirementFormOptions>({
    url: `/requirements/${projectId}/options`,
    method: 'get'
  });
}

/**
 * 从需求表单直接上传来源文档。
 * 后端会把文档类型固定为“需求文档”，并自动提交解析和索引任务。
 */
export function fetchUploadRequirementSourceDocument(
  projectId: number,
  params: Api.RequirementManage.RequirementSourceDocumentUploadParams
) {
  const formData = new FormData();
  formData.append('knowledge_base_id', String(params.knowledgeBaseId));
  formData.append('file', params.file);
  formData.append('metadata', JSON.stringify(params.metadata ?? {}));
  if (params.title) formData.append('title', params.title);
  if (params.moduleId) formData.append('module_id', String(params.moduleId));

  return request<Api.KnowledgeManage.KnowledgeDocument>({
    url: `/requirements/${projectId}/source-documents`,
    method: 'post',
    data: formData
  });
}

/** 创建需求业务记录。 */
export function fetchCreateRequirement(projectId: number, data: Api.RequirementManage.RequirementCreateParams) {
  return request<Api.RequirementManage.Requirement>({
    url: `/requirements/${projectId}`,
    method: 'post',
    data
  });
}

/** 编辑需求业务信息。 */
export function fetchUpdateRequirement(
  projectId: number,
  requirementId: number,
  data: Api.RequirementManage.RequirementUpdateParams
) {
  return request<Api.RequirementManage.Requirement>({
    url: `/requirements/${projectId}/${requirementId}`,
    method: 'put',
    data
  });
}

/** 软删除需求。 */
export function fetchDeleteRequirement(projectId: number, requirementId: number) {
  return request<null>({
    url: `/requirements/${projectId}/${requirementId}`,
    method: 'delete'
  });
}

/** 提交需求拆解任务；默认替换上一批尚未人工确认的 AI 需求点。 */
export function fetchExtractRequirement(
  projectId: number,
  requirementId: number,
  data: Api.RequirementManage.RequirementExtractionSubmitParams = {
    replaceUnconfirmedAiItems: true
  }
) {
  return request<Api.RequirementManage.RequirementExtractionTask>({
    url: `/requirements/${projectId}/${requirementId}/extract`,
    method: 'post',
    data
  });
}

/** 查询某一需求最近提交的拆解任务，用于刷新页面后恢复轮询。 */
export function fetchGetLatestRequirementExtractionTask(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.RequirementExtractionTask | null>({
    url: `/requirements/${projectId}/${requirementId}/extraction-tasks/latest`,
    method: 'get'
  });
}

/** 按任务 ID 查询准确进度，避免重新提交后轮询到旧任务。 */
export function fetchGetRequirementExtractionTask(projectId: number, requirementId: number, taskId: number) {
  return request<Api.RequirementManage.RequirementExtractionTask>({
    url: `/requirements/${projectId}/${requirementId}/extraction-tasks/${taskId}`,
    method: 'get'
  });
}

/** 人工新增原子需求点。 */
export function fetchCreateRequirementItem(
  projectId: number,
  requirementId: number,
  data: Api.RequirementManage.RequirementItemCreateParams
) {
  return request<Api.RequirementManage.RequirementItem>({
    url: `/requirements/${projectId}/${requirementId}/items`,
    method: 'post',
    data
  });
}

/** 人工校正原子需求点。 */
export function fetchUpdateRequirementItem(
  projectId: number,
  requirementId: number,
  itemId: number,
  data: Api.RequirementManage.RequirementItemUpdateParams
) {
  return request<Api.RequirementManage.RequirementItem>({
    url: `/requirements/${projectId}/${requirementId}/items/${itemId}`,
    method: 'put',
    data
  });
}

/** 删除原子需求点。 */
export function fetchDeleteRequirementItem(projectId: number, requirementId: number, itemId: number) {
  return request<null>({
    url: `/requirements/${projectId}/${requirementId}/items/${itemId}`,
    method: 'delete'
  });
}

/** 批量确认原子需求点。 */
export function fetchConfirmRequirementItems(projectId: number, requirementId: number, itemIds: number[]) {
  return request<Api.RequirementManage.RequirementDetail>({
    url: `/requirements/${projectId}/${requirementId}/items/confirm`,
    method: 'post',
    data: { itemIds }
  });
}

/** 分页查询测试用例。 */
export function fetchGetTestCaseList(projectId: number, params: Api.RequirementManage.TestCaseSearchParams) {
  return request<Api.RequirementManage.TestCaseList>({
    url: `/test_cases/${projectId}`,
    method: 'get',
    params
  });
}

/** 查询项目下可供测试用例关联的已确认需求点。 */
export function fetchGetTestCaseRequirementItemOptions(projectId: number) {
  return request<Api.RequirementManage.TestCaseRequirementItemOption[]>({
    url: `/test_cases/${projectId}/requirement-item-options`,
    method: 'get'
  });
}

/** 创建一条人工测试用例。 */
export function fetchCreateTestCase(projectId: number, data: Api.RequirementManage.TestCaseCreateParams) {
  return request<Api.RequirementManage.TestCase>({
    url: `/test_cases/${projectId}`,
    method: 'post',
    data
  });
}

/** 查询一条测试用例及其完整步骤。 */
export function fetchGetTestCaseDetail(projectId: number, testCaseId: number) {
  return request<Api.RequirementManage.TestCase>({
    url: `/test_cases/${projectId}/${testCaseId}`,
    method: 'get'
  });
}

/** 整体更新测试用例及其步骤。 */
export function fetchUpdateTestCase(
  projectId: number,
  testCaseId: number,
  data: Api.RequirementManage.TestCaseCreateParams
) {
  return request<Api.RequirementManage.TestCase>({
    url: `/test_cases/${projectId}/${testCaseId}`,
    method: 'put',
    data
  });
}

/** 把已发布或已停用用例复制为可编辑的新版本草稿。 */
export function fetchCloneTestCaseAsDraft(projectId: number, testCaseId: number) {
  return request<Api.RequirementManage.TestCase>({
    url: `/test_cases/${projectId}/${testCaseId}/clone-draft`,
    method: 'post'
  });
}

/** 软删除测试用例。 */
export function fetchDeleteTestCase(projectId: number, testCaseId: number) {
  return request<null>({
    url: `/test_cases/${projectId}/${testCaseId}`,
    method: 'delete'
  });
}

/** 查询指定需求的覆盖矩阵。 */
export function fetchGetCoverageMatrix(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.CoverageMatrix>({
    url: `/requirements/${projectId}/${requirementId}/coverage`,
    method: 'get'
  });
}

/** 重新检索标准用例并计算覆盖矩阵。 */
export function fetchAnalyzeRequirementCoverage(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.CoverageMatrix>({
    url: `/requirements/${projectId}/${requirementId}/coverage`,
    method: 'post'
  });
}

/** 只针对部分覆盖或未覆盖需求点生成补充用例。 */
export function fetchGenerateMissingCases(projectId: number, requirementId: number) {
  return request<Api.RequirementManage.GenerationTask>({
    url: `/requirements/${projectId}/${requirementId}/generate-cases`,
    method: 'post'
  });
}

/** 分页查询生成任务及审核进度。 */
export function fetchGetGenerationTaskList(
  projectId: number,
  params: Api.RequirementManage.GenerationTaskSearchParams
) {
  return request<Api.RequirementManage.GenerationTaskList>({
    url: `/test_cases/${projectId}/generation-tasks`,
    method: 'get',
    params
  });
}

/** 对 AI 生成的草稿用例执行审核动作。 */
export function fetchReviewGeneratedCase(
  projectId: number,
  testCaseId: number,
  data: Api.RequirementManage.CaseReviewParams
) {
  return request<Api.RequirementManage.TestCase>({
    url: `/test_cases/${projectId}/${testCaseId}/review`,
    method: 'post',
    data
  });
}

/** 在同一个数据库事务中批量接受、驳回或发布测试用例。 */
export function fetchBatchReviewGeneratedCases(projectId: number, data: Api.RequirementManage.CaseBatchReviewParams) {
  return request<Api.RequirementManage.TestCase[]>({
    url: `/test_cases/batch-review/${projectId}`,
    method: 'post',
    data
  });
}
