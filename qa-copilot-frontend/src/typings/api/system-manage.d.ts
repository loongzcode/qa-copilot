declare namespace Api {
  /**
   * namespace SystemManage
   *
   * backend api module: "systemManage"
   */
  namespace SystemManage {
    type CommonSearchParams = Pick<Common.PaginatingCommonParams, 'current' | 'size'>;

    /** role */
    type Role = Common.CommonRecord<{
      /** role name */
      roleName: string;
      /** role code */
      roleCode: string;
      /** role description */
      roleDesc: string;
    }>;

    /** role search params */
    type RoleSearchParams = CommonType.RecordNullable<
      Pick<Api.SystemManage.Role, 'roleName' | 'roleCode' | 'status'> & CommonSearchParams
    >;

    /** role list */
    type RoleList = Common.PaginatingQueryRecord<Role>;

    /** all role */
    type AllRole = Pick<Role, 'id' | 'roleName' | 'roleCode'>;

    /**
     * user gender
     *
     * - "1": "male"
     * - "2": "female"
     */
    type UserGender = '1' | '2';

    /** user returned by the existing frontend mock/system-manage APIs */
    type User = Common.CommonRecord<{
      userName: string;
      userGender: UserGender | undefined;
      nickName: string;
      userPhone: string;
      userEmail: string;
      userRoles: string[];
    }>;

    type UserSearchParams = CommonType.RecordNullable<
      Pick<User, 'userName' | 'userGender' | 'nickName' | 'userPhone' | 'userEmail' | 'status'> & CommonSearchParams
    >;

    type UserList = Common.PaginatingQueryRecord<User>;

    /** user returned by FastAPI */
    type FastApiUser = {
      id: number;
      username: string;
      displayName: string;
      isActive: boolean;
      isSuperuser: boolean;
      roleIds: number[];
      roleCodes: string[];
      createdAt: string;
      updatedAt: string;
    };

    type FastApiUserCreateParams = {
      username: string;
      displayName: string;
      password: string;
      isActive: boolean;
      roleIds: number[];
    };

    type FastApiUserUpdateParams = {
      displayName: string;
      password?: string;
      isActive: boolean;
      roleIds: number[];
    };

    /** user search params */
    type FastApiUserSearchParams = CommonType.RecordNullable<CommonSearchParams & { keyword: string }>;

    type FastApiUserList = Common.PaginatingQueryRecord<FastApiUser>;

    type FastApiRoleOption = {
      id: number;
      name: string;
      code: string;
    };

    type FastApiRole = {
      id: number;
      code: string;
      name: string;
      description: string;
      enabled: boolean;
      isSystem: boolean;
      menuIds: number[];
      createdAt: string;
      updatedAt: string;
    };

    type FastApiRoleCreateParams = {
      code: string;
      name: string;
      description: string;
      enabled: boolean;
      menuIds: number[];
    };

    type FastApiRoleUpdateParams = {
      name?: string;
      description?: string;
      enabled?: boolean;
      menuIds?: number[];
    };

    type FastApiMenuType = 'directory' | 'page' | 'button';

    type FastApiMenu = {
      id: number;
      parentId: number | null;
      routeName: string;
      path: string;
      component: string;
      title: string;
      icon: string;
      order: number;
      menuType: FastApiMenuType;
      permissionCode: string | null;
      enabled: boolean;
      hidden: boolean;
      createdAt: string;
      updatedAt: string;
    };

    type FastApiMenuCreateParams = Omit<FastApiMenu, 'id' | 'createdAt' | 'updatedAt'>;

    type FastApiMenuUpdateParams = Partial<
      Pick<
        FastApiMenu,
        | 'parentId'
        | 'path'
        | 'component'
        | 'title'
        | 'icon'
        | 'order'
        | 'menuType'
        | 'permissionCode'
        | 'enabled'
        | 'hidden'
      >
    >;

    /**
     * menu type
     *
     * - "1": directory
     * - "2": menu
     */
    type MenuType = '1' | '2';

    type MenuButton = {
      /**
       * button code
       *
       * it can be used to control the button permission
       */
      code: string;
      /** button description */
      desc: string;
    };

    /**
     * icon type
     *
     * - "1": iconify icon
     * - "2": local icon
     */
    type IconType = '1' | '2';

    type MenuPropsOfRoute = Pick<
      import('vue-router').RouteMeta,
      | 'i18nKey'
      | 'keepAlive'
      | 'constant'
      | 'order'
      | 'href'
      | 'hideInMenu'
      | 'activeMenu'
      | 'multiTab'
      | 'fixedIndexInTab'
      | 'query'
    >;

    type Menu = Common.CommonRecord<{
      /** parent menu id */
      parentId: number;
      /** menu type */
      menuType: MenuType;
      /** menu name */
      menuName: string;
      /** route name */
      routeName: string;
      /** route path */
      routePath: string;
      /** component */
      component?: string;
      /** iconify icon name or local icon name */
      icon: string;
      /** icon type */
      iconType: IconType;
      /** buttons */
      buttons?: MenuButton[] | null;
      /** children menu */
      children?: Menu[] | null;
    }> &
      MenuPropsOfRoute;

    /** menu list */
    type MenuList = Common.PaginatingQueryRecord<Menu>;

    type MenuTree = {
      id: number;
      label: string;
      pId: number;
      children?: MenuTree[];
    };
  }
}
