import { request } from '../request';

export function fetchGetTools() {
  return request<Api.ToolManage.ToolDefinition[]>({ url: '/tools', method: 'get' });
}
export function fetchGetToolConnections(projectId: number) {
  return request<Api.ToolManage.Connection[]>({ url: `/projects/${projectId}/connections`, method: 'get' });
}
export function fetchCreateToolConnection(projectId: number, data: Api.ToolManage.ConnectionCreateParams) {
  return request<Api.ToolManage.Connection>({ url: `/projects/${projectId}/connections`, method: 'post', data });
}
export function fetchUpdateToolConnection(
  projectId: number,
  connectionId: number,
  data: Api.ToolManage.ConnectionUpdateParams
) {
  return request<Api.ToolManage.Connection>({
    url: `/projects/${projectId}/connections/${connectionId}`,
    method: 'put',
    data
  });
}
export function fetchDeleteToolConnection(projectId: number, connectionId: number) {
  return request<null>({ url: `/projects/${projectId}/connections/${connectionId}`, method: 'delete' });
}
export function fetchGetFileTemplates(projectId: number) {
  return request<Api.ToolManage.FileTemplate[]>({ url: `/projects/${projectId}/file-templates`, method: 'get' });
}
export function fetchCreateFileTemplate(projectId: number, data: Api.ToolManage.FileTemplateParams) {
  return request<Api.ToolManage.FileTemplate>({ url: `/projects/${projectId}/file-templates`, method: 'post', data });
}
export function fetchUpdateFileTemplate(
  projectId: number,
  templateId: number,
  data: Api.ToolManage.FileTemplateParams
) {
  return request<Api.ToolManage.FileTemplate>({
    url: `/projects/${projectId}/file-templates/${templateId}`,
    method: 'put',
    data
  });
}
export function fetchGenerateAIFileRecords(
  projectId: number,
  templateId: number,
  data: Api.ToolManage.AIFileRecordsGenerateParams
) {
  return request<Api.ToolManage.AIFileRecordsPreview>({
    url: `/projects/${projectId}/file-templates/${templateId}/ai-records`,
    method: 'post',
    data,
    timeout: 120000
  });
}
export function fetchCreateToolTask(projectId: number, data: Api.ToolManage.TaskCreateParams) {
  return request<Api.ToolManage.Task>({ url: `/projects/${projectId}/tool-tasks`, method: 'post', data });
}
export function fetchGetToolTasks(projectId: number, params: Api.ToolManage.TaskSearchParams) {
  return request<Api.ToolManage.TaskList>({ url: `/projects/${projectId}/tool-tasks`, method: 'get', params });
}
export function fetchGetToolTask(projectId: number, taskId: number) {
  return request<Api.ToolManage.Task>({ url: `/projects/${projectId}/tool-tasks/${taskId}`, method: 'get' });
}
export function fetchPreviewToolTask(projectId: number, taskId: number) {
  return request<Api.ToolManage.Task>({ url: `/projects/${projectId}/tool-tasks/${taskId}/preview`, method: 'post' });
}
export function fetchApproveToolTask(
  projectId: number,
  taskId: number,
  data: { decision: 'APPROVED' | 'REJECTED'; comment: string }
) {
  return request<Api.ToolManage.Task>({
    url: `/projects/${projectId}/tool-tasks/${taskId}/approval`,
    method: 'post',
    data
  });
}
export function fetchExecuteToolTask(projectId: number, taskId: number) {
  return request<Api.ToolManage.Task>({ url: `/projects/${projectId}/tool-tasks/${taskId}/execute`, method: 'post' });
}
export function fetchRollbackToolTask(projectId: number, taskId: number) {
  return request<Api.ToolManage.Task>({ url: `/projects/${projectId}/tool-tasks/${taskId}/rollback`, method: 'post' });
}
export function fetchUploadToolInputFile(projectId: number, taskId: number, file: File) {
  const data = new FormData();
  data.append('file', file);
  return request<Api.ToolManage.Task>({
    url: `/projects/${projectId}/tool-tasks/${taskId}/input-file`,
    method: 'post',
    data
  });
}
export function getToolArtifactUrl(projectId: number, taskId: number, artifactId: number) {
  return `/api/projects/${projectId}/tool-tasks/${taskId}/artifacts/${artifactId}`;
}
