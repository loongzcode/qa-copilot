import { computed, reactive, ref } from 'vue';

export type ProjectStatus = 'active' | 'archived';
export type ProjectRole = 'OWNER' | 'MANAGER' | 'MEMBER' | 'VIEWER';

export interface ProjectRecord {
  id: number;
  code: string;
  name: string;
  description: string;
  owner: string;
  memberCount: number;
  moduleCount: number;
  status: ProjectStatus;
  updatedAt: string;
}

export interface ProjectMember {
  id: number;
  projectId: number;
  name: string;
  username: string;
  role: ProjectRole;
  joinedAt: string;
}

export interface ProjectModule {
  id: number;
  projectId: number;
  parentId: number | null;
  name: string;
  code: string;
  description: string;
  assetCount: number;
  children?: ProjectModule[];
}

export interface TestEnvironment {
  id: number;
  projectId: number;
  name: string;
  baseUrl: string;
  allowedHosts: string[];
  variables: Array<{ key: string; value: string; secret: boolean }>;
  enabled: boolean;
  updatedAt: string;
}

export const projects = ref<ProjectRecord[]>([
  {
    id: 1,
    code: 'PAYMENT',
    name: '支付结算平台',
    description: '支付、退款、对账与清结算相关测试资产。',
    owner: '林晓',
    memberCount: 8,
    moduleCount: 6,
    status: 'active',
    updatedAt: '2026-08-16 15:32'
  },
  {
    id: 2,
    code: 'MEMBER',
    name: '会员中心',
    description: '会员注册、等级、权益与积分服务。',
    owner: '周宁',
    memberCount: 5,
    moduleCount: 4,
    status: 'active',
    updatedAt: '2026-08-15 11:08'
  },
  {
    id: 3,
    code: 'LEGACY-CRM',
    name: '旧版客户系统',
    description: '历史项目，仅保留测试资产查询。',
    owner: '王哲',
    memberCount: 3,
    moduleCount: 3,
    status: 'archived',
    updatedAt: '2026-07-28 09:41'
  }
]);

export const members = ref<ProjectMember[]>([
  { id: 1, projectId: 1, name: '林晓', username: 'linxiao', role: 'OWNER', joinedAt: '2026-06-12' },
  { id: 2, projectId: 1, name: '陈思远', username: 'chensiyuan', role: 'MANAGER', joinedAt: '2026-06-13' },
  { id: 3, projectId: 1, name: '赵晴', username: 'zhaoqing', role: 'MEMBER', joinedAt: '2026-06-18' },
  { id: 4, projectId: 1, name: '顾言', username: 'guyan', role: 'VIEWER', joinedAt: '2026-07-02' },
  { id: 5, projectId: 2, name: '周宁', username: 'zhouning', role: 'OWNER', joinedAt: '2026-05-20' },
  { id: 6, projectId: 2, name: '叶可', username: 'yeke', role: 'MEMBER', joinedAt: '2026-05-23' }
]);

export const projectModules = ref<ProjectModule[]>([
  {
    id: 1,
    projectId: 1,
    parentId: null,
    name: '支付',
    code: 'PAY',
    description: '支付核心流程',
    assetCount: 42,
    children: [
      { id: 2, projectId: 1, parentId: 1, name: '收银台', code: 'CASHIER', description: '聚合收银台', assetCount: 18 },
      {
        id: 3,
        projectId: 1,
        parentId: 1,
        name: '支付订单',
        code: 'ORDER',
        description: '订单与状态流转',
        assetCount: 24
      }
    ]
  },
  { id: 4, projectId: 1, parentId: null, name: '退款', code: 'REFUND', description: '退款申请与审核', assetCount: 16 },
  { id: 5, projectId: 1, parentId: null, name: '对账', code: 'RECON', description: '渠道与商户对账', assetCount: 11 },
  {
    id: 6,
    projectId: 2,
    parentId: null,
    name: '会员账户',
    code: 'ACCOUNT',
    description: '注册与账户资料',
    assetCount: 21
  },
  {
    id: 7,
    projectId: 2,
    parentId: null,
    name: '会员权益',
    code: 'BENEFIT',
    description: '等级与权益发放',
    assetCount: 13
  }
]);

export const environments = ref<TestEnvironment[]>([
  {
    id: 1,
    projectId: 1,
    name: 'SIT 测试环境',
    baseUrl: 'https://sit-api.example.internal',
    allowedHosts: ['sit-api.example.internal', 'mock.example.internal'],
    variables: [
      { key: 'tenant_id', value: 'qa-team', secret: false },
      { key: 'api_token', value: '********', secret: true }
    ],
    enabled: true,
    updatedAt: '2026-08-16 16:20'
  },
  {
    id: 2,
    projectId: 1,
    name: 'UAT 验收环境',
    baseUrl: 'https://uat-api.example.internal',
    allowedHosts: ['uat-api.example.internal'],
    variables: [{ key: 'tenant_id', value: 'uat-team', secret: false }],
    enabled: true,
    updatedAt: '2026-08-12 09:18'
  },
  {
    id: 3,
    projectId: 2,
    name: '会员 SIT',
    baseUrl: 'https://member-sit.example.internal',
    allowedHosts: ['member-sit.example.internal'],
    variables: [],
    enabled: false,
    updatedAt: '2026-08-10 14:05'
  }
]);

export const activeProjectId = ref(1);
export const activeProjects = computed(() => projects.value.filter(item => item.status === 'active'));
export const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));

export function nextId(records: Array<{ id: number }>) {
  return Math.max(0, ...records.map(item => item.id)) + 1;
}

export function nowText() {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function createEmptyProject(): ProjectRecord {
  return reactive({
    id: 0,
    code: '',
    name: '',
    description: '',
    owner: '',
    memberCount: 1,
    moduleCount: 0,
    status: 'active',
    updatedAt: nowText()
  });
}
