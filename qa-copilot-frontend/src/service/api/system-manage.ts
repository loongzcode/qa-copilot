import { request } from '../request';

/** get role list */
export function fetchGetRoleList(params?: Api.SystemManage.RoleSearchParams) {
  return request<Api.SystemManage.RoleList>({
    url: '/systemManage/getRoleList',
    method: 'get',
    params
  });
}

/**
 * get all roles
 *
 * these roles are all enabled
 */
export function fetchGetAllRoles() {
  return request<Api.SystemManage.AllRole[]>({
    url: '/systemManage/getAllRoles',
    method: 'get'
  });
}

/** get user list */
export function fetchGetUserList(params?: Api.SystemManage.UserSearchParams) {
  return request<Api.SystemManage.UserList>({
    url: '/systemManage/getUserList',
    method: 'get',
    params
  });
}

/** get users from FastAPI */
export function fetchGetFastApiUserList(params?: Api.SystemManage.FastApiUserSearchParams) {
  return request<Api.SystemManage.FastApiUserList>({
    url: '/user/list',
    method: 'get',
    params
  });
}

/** create a user through FastAPI */
export function fetchCreateFastApiUser(data: Api.SystemManage.FastApiUserCreateParams) {
  return request<Api.SystemManage.FastApiUser>({
    url: '/user/create',
    method: 'post',
    data
  });
}

/** update a user through FastAPI */
export function fetchUpdateFastApiUser(userId: number, data: Api.SystemManage.FastApiUserUpdateParams) {
  return request<Api.SystemManage.FastApiUser>({
    url: `/user/update/${userId}`,
    method: 'put',
    data
  });
}

/** delete a user through FastAPI */
export function fetchDeleteFastApiUser(userId: number) {
  return request<Api.SystemManage.FastApiUser>({
    url: `/user/delete/${userId}`,
    method: 'delete'
  });
}

/** get enabled role options from FastAPI */
export function fetchGetFastApiRoleOptions() {
  return request<Api.SystemManage.FastApiRoleOption[]>({
    url: '/role/options',
    method: 'get'
  });
}

/** get roles from FastAPI */
export function fetchGetFastApiRoleList() {
  return request<Api.SystemManage.FastApiRole[]>({ url: '/role/list', method: 'get' });
}

/** create a role through FastAPI */
export function fetchCreateFastApiRole(data: Api.SystemManage.FastApiRoleCreateParams) {
  return request<Api.SystemManage.FastApiRole>({ url: '/role/create', method: 'post', data });
}

/** update a role through FastAPI */
export function fetchUpdateFastApiRole(roleId: number, data: Api.SystemManage.FastApiRoleUpdateParams) {
  return request<Api.SystemManage.FastApiRole>({ url: `/role/update/${roleId}`, method: 'put', data });
}

/** delete a role through FastAPI */
export function fetchDeleteFastApiRole(roleId: number) {
  return request<Api.SystemManage.FastApiRole>({ url: `/role/delete/${roleId}`, method: 'delete' });
}

/** get menus from FastAPI */
export function fetchGetFastApiMenuList() {
  return request<Api.SystemManage.FastApiMenu[]>({ url: '/menu/list', method: 'get' });
}

/** create a menu through FastAPI */
export function fetchCreateFastApiMenu(data: Api.SystemManage.FastApiMenuCreateParams) {
  return request<Api.SystemManage.FastApiMenu>({ url: '/menu/create', method: 'post', data });
}

/** update a menu through FastAPI */
export function fetchUpdateFastApiMenu(menuId: number, data: Api.SystemManage.FastApiMenuUpdateParams) {
  return request<Api.SystemManage.FastApiMenu>({ url: `/menu/update/${menuId}`, method: 'put', data });
}

/** delete a menu through FastAPI */
export function fetchDeleteFastApiMenu(menuId: number) {
  return request<null>({ url: `/menu/delete/${menuId}`, method: 'delete' });
}

/** get menu list */
export function fetchGetMenuList() {
  return request<Api.SystemManage.MenuList>({
    url: '/systemManage/getMenuList/v2',
    method: 'get'
  });
}

/** get all pages */
export function fetchGetAllPages() {
  return request<string[]>({
    url: '/systemManage/getAllPages',
    method: 'get'
  });
}

/** get menu tree */
export function fetchGetMenuTree() {
  return request<Api.SystemManage.MenuTree[]>({
    url: '/systemManage/getMenuTree',
    method: 'get'
  });
}
