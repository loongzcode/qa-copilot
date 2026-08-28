import { request } from '../request';

/** 分页查询项目内的自动化定义版本。 */
export function fetchGetAutomationDefinitionList(
  projectId: number,
  params: Api.AutomationManage.DefinitionSearchParams
) {
  return request<Api.AutomationManage.DefinitionList>({
    url: `/automation-definitions/${projectId}`,
    method: 'get',
    params
  });
}

/** 从已发布、可自动化的 API 测试用例创建新草稿版本。 */
export function fetchCreateAutomationDefinition(projectId: number, testCaseId: number) {
  return request<Api.AutomationManage.Definition>({
    url: `/automation-definitions/${projectId}/from-test-case/${testCaseId}`,
    method: 'post'
  });
}

/** 保存已经通过前后端协议校验的草稿 JSON。 */
export function fetchUpdateAutomationDefinition(
  projectId: number,
  definitionId: number,
  data: Api.AutomationManage.DefinitionUpdateParams
) {
  return request<Api.AutomationManage.Definition>({
    url: `/automation-definitions/${projectId}/${definitionId}`,
    method: 'put',
    data
  });
}

/** 审批草稿；服务端会同时退出同一用例的旧审批版本。 */
export function fetchApproveAutomationDefinition(projectId: number, definitionId: number) {
  return request<Api.AutomationManage.Definition>({
    url: `/automation-definitions/${projectId}/${definitionId}/approve`,
    method: 'post'
  });
}

/** 将已审批定义退出后续执行候选。 */
export function fetchRetireAutomationDefinition(projectId: number, definitionId: number) {
  return request<Api.AutomationManage.Definition>({
    url: `/automation-definitions/${projectId}/${definitionId}/retire`,
    method: 'post'
  });
}

/** 软删除草稿或已退出定义。 */
export function fetchDeleteAutomationDefinition(projectId: number, definitionId: number) {
  return request<null>({
    url: `/automation-definitions/${projectId}/${definitionId}`,
    method: 'delete'
  });
}

/** 查询自动化定义从创建、编辑到审批或退出的不可变审计时间线。 */
export function fetchGetAutomationDefinitionChanges(projectId: number, definitionId: number) {
  return request<Api.AutomationManage.DefinitionChange[]>({
    url: `/automation-definitions/${projectId}/${definitionId}/changes`,
    method: 'get'
  });
}

/** 分页查询项目内的后台自动化执行任务。 */
export function fetchGetAutomationExecutionList(projectId: number, params: Api.AutomationManage.ExecutionSearchParams) {
  return request<Api.AutomationManage.ExecutionTaskList>({
    url: `/automation-executions/${projectId}`,
    method: 'get',
    params
  });
}

/** 使用已审批定义和非生产环境提交后台执行任务。 */
export function fetchSubmitAutomationExecution(projectId: number, data: Api.AutomationManage.ExecutionCreateParams) {
  return request<Api.AutomationManage.ExecutionTask>({
    url: `/automation-executions/${projectId}`,
    method: 'post',
    data
  });
}

/** 取消等待任务，或通知 Worker 终止运行中的 Pytest 子进程。 */
export function fetchCancelAutomationExecution(projectId: number, taskId: number) {
  return request<Api.AutomationManage.ExecutionTask>({
    url: `/automation-executions/${projectId}/${taskId}/cancel`,
    method: 'post'
  });
}

/** 查询任务汇总和逐步骤脱敏执行报告。 */
export function fetchGetAutomationExecutionReport(projectId: number, taskId: number) {
  return request<Api.AutomationManage.ExecutionReport>({
    url: `/automation-executions/${projectId}/${taskId}`,
    method: 'get'
  });
}

export function fetchGetAutomationSchedules(projectId: number) {
  return request<Api.AutomationManage.Schedule[]>({ url: `/automation-schedules/${projectId}`, method: 'get' });
}

export function fetchCreateAutomationSchedule(projectId: number, data: Api.AutomationManage.ScheduleParams) {
  return request<Api.AutomationManage.Schedule>({ url: `/automation-schedules/${projectId}`, method: 'post', data });
}

export function fetchUpdateAutomationSchedule(
  projectId: number,
  scheduleId: number,
  data: Api.AutomationManage.ScheduleParams
) {
  return request<Api.AutomationManage.Schedule>({
    url: `/automation-schedules/${projectId}/${scheduleId}`,
    method: 'put',
    data
  });
}

export function fetchDeleteAutomationSchedule(projectId: number, scheduleId: number) {
  return request<null>({ url: `/automation-schedules/${projectId}/${scheduleId}`, method: 'delete' });
}
