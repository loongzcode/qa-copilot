import { request } from '../request';

/** 分页查询项目信息。 */
export function fetchGetProjectList(params: Api.ProjectManage.ProjectSearchParams) {
  return request<Api.ProjectManage.ProjectList>({
    url: '/projects/list',
    method: 'get',
    params
  });
}

/** 创建项目。 */
export function fetchCreateProject(data: Api.ProjectManage.ProjectCreateParams) {
  return request<Api.ProjectManage.Project>({
    url: '/projects/create',
    method: 'post',
    data
  });
}

/** 编辑项目。 */
export function fetchUpdateProject(projectId: number, data: Api.ProjectManage.ProjectUpdateParams) {
  return request<Api.ProjectManage.Project>({
    url: `/projects/update/${projectId}`,
    method: 'put',
    data
  });
}

/** 归档项目。 */
export function fetchArchiveProject(projectId: number) {
  return request<Api.ProjectManage.Project>({
    url: `/projects/archive/${projectId}`,
    method: 'put'
  });
}

/** 启动项目。 */
export function fetchStartProject(projectId: number) {
  return request<Api.ProjectManage.Project>({
    url: `/projects/start/${projectId}`,
    method: 'put'
  });
}

/** 分页查询项目成员。 */
export function fetchGetProjectMemberList(projectId: number, params: Api.ProjectManage.ProjectMemberSearchParams) {
  return request<Api.ProjectManage.ProjectMemberList>({
    url: `/test-projects/${projectId}/members`,
    method: 'get',
    params
  });
}

/** 查询当前项目可添加的用户。 */
export function fetchGetProjectMemberOptions(
  projectId: number,
  params: Api.ProjectManage.ProjectMemberOptionSearchParams
) {
  return request<Api.ProjectManage.ProjectMemberOption[]>({
    url: `/test-projects/${projectId}/member-options`,
    method: 'get',
    params
  });
}

/** 添加项目成员。 */
export function fetchCreateProjectMember(projectId: number, data: Api.ProjectManage.ProjectMemberCreateParams) {
  return request<Api.ProjectManage.ProjectMember>({
    url: `/test-projects/${projectId}/members`,
    method: 'post',
    data
  });
}

/** 修改项目成员角色。 */
export function fetchUpdateProjectMember(
  projectId: number,
  userId: number,
  data: Api.ProjectManage.ProjectMemberUpdateParams
) {
  return request<Api.ProjectManage.ProjectMember>({
    url: `/test-projects/${projectId}/members/${userId}`,
    method: 'put',
    data
  });
}

/** 移除项目成员。 */
export function fetchDeleteProjectMember(projectId: number, userId: number) {
  return request<null>({
    url: `/test-projects/${projectId}/members/${userId}`,
    method: 'delete'
  });
}

/** 查询项目功能模块树。 */
export function fetchGetProjectModules(projectId: number, params: Api.ProjectManage.ProjectModuleSearchParams) {
  return request<Api.ProjectManage.ProjectModule[]>({
    url: `/test_modules/${projectId}/modules`,
    method: 'get',
    params
  });
}

/** 创建项目功能模块。 */
export function fetchCreateProjectModule(projectId: number, data: Api.ProjectManage.ProjectModuleCreateParams) {
  return request<Api.ProjectManage.ProjectModule>({
    url: `/test_modules/${projectId}/modules`,
    method: 'post',
    data
  });
}

/** 编辑项目功能模块。 */
export function fetchUpdateProjectModule(
  projectId: number,
  moduleId: number,
  data: Api.ProjectManage.ProjectModuleUpdateParams
) {
  return request<Api.ProjectManage.ProjectModule>({
    url: `/test_modules/${projectId}/modules/${moduleId}`,
    method: 'put',
    data
  });
}

/** 删除项目功能模块及其子模块。 */
export function fetchDeleteProjectModule(projectId: number, moduleId: number) {
  return request<null>({
    url: `/test_modules/${projectId}/modules/${moduleId}`,
    method: 'delete'
  });
}

/** 查询项目测试环境。 */
export function fetchGetTestEnvironments(projectId: number, params: Api.ProjectManage.TestEnvironmentSearchParams) {
  return request<Api.ProjectManage.TestEnvironment[]>({
    url: `/test_environments/${projectId}/environments`,
    method: 'get',
    params
  });
}

/** 创建项目测试环境。 */
export function fetchCreateTestEnvironment(projectId: number, data: Api.ProjectManage.TestEnvironmentCreateParams) {
  return request<Api.ProjectManage.TestEnvironment>({
    url: `/test_environments/${projectId}/environments`,
    method: 'post',
    data
  });
}

/** 编辑项目测试环境。 */
export function fetchUpdateTestEnvironment(
  projectId: number,
  environmentId: number,
  data: Api.ProjectManage.TestEnvironmentUpdateParams
) {
  return request<Api.ProjectManage.TestEnvironment>({
    url: `/test_environments/${projectId}/environments/${environmentId}`,
    method: 'put',
    data
  });
}

/** 删除项目测试环境。 */
export function fetchDeleteTestEnvironment(projectId: number, environmentId: number) {
  return request<null>({
    url: `/test_environments/${projectId}/environments/${environmentId}`,
    method: 'delete'
  });
}

/** 测试项目环境的网络连接。 */
export function fetchTestEnvironmentConnection(projectId: number, environmentId: number) {
  return request<Api.ProjectManage.TestEnvironmentConnectionResult>({
    url: `/test_environments/${projectId}/environments/${environmentId}/test`,
    method: 'post'
  });
}
