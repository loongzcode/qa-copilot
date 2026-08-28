declare namespace Api {
  /** 项目管理接口。 */
  namespace ProjectManage {
    type ProjectStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED';

    type Project = {
      id: number;
      name: string;
      code: string;
      description: string;
      ownerId: number | null;
      ownerName: string | null;
      memberCount: number;
      moduleCount: number;
      status: ProjectStatus;
      updatedAt: string;
    };

    type ProjectSearchParams = {
      current: number;
      size: number;
      keyword: string;
      status?: ProjectStatus;
    };

    type ProjectCreateParams = {
      name: string;
      code: string;
      description: string;
      ownerId: number | null;
    };

    type ProjectUpdateParams = {
      name?: string;
      description?: string;
      ownerId?: number | null;
    };

    type ProjectList = Common.PaginatingQueryRecord<Project>;

    type ProjectMemberRole = 'OWNER' | 'MANAGER' | 'MEMBER' | 'VIEWER';

    type ProjectMember = {
      projectId: number;
      userId: number;
      username: string;
      displayName: string;
      memberRole: ProjectMemberRole;
      createdAt: string;
    };

    type ProjectMemberSearchParams = {
      current: number;
      size: number;
      keyword: string;
    };

    type ProjectMemberCreateParams = {
      userId: number;
      memberRole: ProjectMemberRole;
    };

    type ProjectMemberUpdateParams = {
      memberRole: ProjectMemberRole;
    };

    type ProjectMemberOption = {
      userId: number;
      username: string;
      displayName: string;
    };

    type ProjectMemberOptionSearchParams = {
      keyword: string;
      limit: number;
    };

    type ProjectMemberList = Common.PaginatingQueryRecord<ProjectMember>;

    type ProjectModule = {
      id: number;
      projectId: number;
      parentId: number | null;
      name: string;
      code: string;
      description: string;
      orderNo: number;
      assetCount: number;
      createdAt: string;
      updatedAt: string;
      children: ProjectModule[];
    };

    type ProjectModuleSearchParams = {
      keyword: string;
    };

    type ProjectModuleCreateParams = {
      parentId: number | null;
      name: string;
      code: string;
      description: string;
      orderNo: number;
    };

    type ProjectModuleUpdateParams = {
      parentId?: number | null;
      name?: string;
      code?: string;
      description?: string;
      orderNo?: number;
    };

    type TestEnvironmentVariable = {
      key: string;
      value: string;
      secret: boolean;
    };

    /** 环境用途；生产环境禁止被自动化执行器访问。 */
    type TestEnvironmentType = 'LOCAL' | 'DEVELOPMENT' | 'TEST' | 'STAGING' | 'PRODUCTION';

    type TestEnvironment = {
      id: number;
      projectId: number;
      name: string;
      environmentType: TestEnvironmentType;
      baseUrl: string;
      allowedHosts: string[];
      headers: Record<string, string>;
      variables: TestEnvironmentVariable[];
      variableCount: number;
      enabled: boolean;
      createdBy: number | null;
      createdByName: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type TestEnvironmentSearchParams = {
      keyword: string;
      enabled?: boolean;
    };

    type TestEnvironmentCreateParams = {
      name: string;
      environmentType: TestEnvironmentType;
      baseUrl: string;
      allowedHosts: string[];
      headers: Record<string, string>;
      variables: TestEnvironmentVariable[];
      enabled: boolean;
    };

    type TestEnvironmentUpdateParams = Partial<TestEnvironmentCreateParams>;

    type TestEnvironmentConnectionResult = {
      success: boolean;
      statusCode: number | null;
      latencyMs: number;
      message: string;
    };
  }
}
