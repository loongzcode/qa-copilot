import { request } from '../request';

/** 为项目内的开放目标生成受权限约束的执行计划；当前接口只规划，不执行步骤。 */
export function fetchCreateSupervisorRun(projectId: number, data: Api.Supervisor.CreateRunParams) {
  return request<Api.Supervisor.RunDetail>({
    url: `/supervisor/projects/${projectId}/runs`,
    method: 'post',
    data,
    // 规划需要等待大模型返回，不能沿用普通 CRUD 的短超时。
    timeout: 120000
  });
}

/** 分页查询项目内的 Supervisor 运行记录。 */
export function fetchGetSupervisorRuns(projectId: number, params: Api.Supervisor.RunSearchParams) {
  return request<Api.Supervisor.RunList>({
    url: `/supervisor/projects/${projectId}/runs`,
    method: 'get',
    params
  });
}

/** 查询一次运行的完整计划、参数快照和安全判定。 */
export function fetchGetSupervisorRunDetail(projectId: number, runId: number) {
  return request<Api.Supervisor.RunDetail>({
    url: `/supervisor/projects/${projectId}/runs/${runId}`,
    method: 'get'
  });
}

/** 取消尚未进入实际执行阶段的 Supervisor 运行。 */
export function fetchCancelSupervisorRun(projectId: number, runId: number) {
  return request<Api.Supervisor.RunDetail>({
    url: `/supervisor/projects/${projectId}/runs/${runId}/cancel`,
    method: 'post'
  });
}

/** 将已就绪计划可靠地提交给 Supervisor 专用后台 Worker。 */
export function fetchExecuteSupervisorRun(projectId: number, runId: number) {
  return request<Api.Supervisor.RunDetail>({
    url: `/supervisor/projects/${projectId}/runs/${runId}/execute`,
    method: 'post'
  });
}

/** 审批风险步骤；最后一个等待步骤获批后，后端会自动可靠提交执行。 */
export function fetchDecideSupervisorStepApproval(
  projectId: number,
  runId: number,
  stepId: number,
  data: Api.Supervisor.ApprovalParams
) {
  return request<Api.Supervisor.RunDetail>({
    url: `/supervisor/projects/${projectId}/runs/${runId}/steps/${stepId}/approval`,
    method: 'post',
    data
  });
}
