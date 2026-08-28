import { ref } from 'vue';

export type KnowledgeVisibility = 'PROJECT' | 'MANAGERS' | 'PRIVATE';
export type KnowledgeDocumentType =
  | 'STANDARD_CASE'
  | 'TEST_PROCESS'
  | 'OPERATION_GUIDE'
  | 'SYSTEM_DESIGN'
  | 'REQUIREMENT'
  | 'API_DOCUMENT'
  | 'DEFECT_EXPERIENCE'
  | 'OTHER';
export type DocumentParseStatus = 'PENDING' | 'PARSING' | 'INDEXING' | 'READY' | 'FAILED';

export interface KnowledgeBaseRecord {
  id: number;
  projectId: number;
  name: string;
  description: string;
  visibility: KnowledgeVisibility;
  embeddingModelName: string;
  rerankModelName: string;
  documentCount: number;
  chunkCount: number;
  enabled: boolean;
  updatedAt: string;
}

export interface KnowledgeDocumentRecord {
  id: number;
  projectId: number;
  knowledgeBaseId: number;
  title: string;
  fileName: string;
  documentType: KnowledgeDocumentType;
  moduleName: string;
  version: number;
  parseStatus: DocumentParseStatus;
  chunkCount: number;
  fileSize: string;
  updatedAt: string;
  errorMessage?: string;
}

export const knowledgeBases = ref<KnowledgeBaseRecord[]>([
  {
    id: 1,
    projectId: 0,
    name: '项目测试知识库',
    description: '沉淀测试流程、系统设计、接口文档与历史标准用例。',
    visibility: 'PROJECT',
    embeddingModelName: 'text-embedding-3-small',
    rerankModelName: 'bge-reranker-v2-m3',
    documentCount: 12,
    chunkCount: 368,
    enabled: true,
    updatedAt: '2026-08-18 16:30'
  },
  {
    id: 2,
    projectId: 0,
    name: '缺陷经验库',
    description: '记录线上与测试阶段典型缺陷、根因和回归关注点。',
    visibility: 'MANAGERS',
    embeddingModelName: 'text-embedding-3-small',
    rerankModelName: 'bge-reranker-v2-m3',
    documentCount: 5,
    chunkCount: 96,
    enabled: true,
    updatedAt: '2026-08-17 10:12'
  }
]);

export const knowledgeDocuments = ref<KnowledgeDocumentRecord[]>([
  {
    id: 1,
    projectId: 0,
    knowledgeBaseId: 1,
    title: '支付系统测试流程',
    fileName: '支付系统测试流程.pdf',
    documentType: 'TEST_PROCESS',
    moduleName: '支付订单',
    version: 3,
    parseStatus: 'READY',
    chunkCount: 48,
    fileSize: '2.4 MB',
    updatedAt: '2026-08-18 15:42'
  },
  {
    id: 2,
    projectId: 0,
    knowledgeBaseId: 1,
    title: '退款接口文档',
    fileName: 'refund-api.md',
    documentType: 'API_DOCUMENT',
    moduleName: '退款',
    version: 2,
    parseStatus: 'INDEXING',
    chunkCount: 0,
    fileSize: '86 KB',
    updatedAt: '2026-08-18 16:26'
  },
  {
    id: 3,
    projectId: 0,
    knowledgeBaseId: 1,
    title: '对账平台系统设计',
    fileName: '对账平台系统设计.docx',
    documentType: 'SYSTEM_DESIGN',
    moduleName: '对账',
    version: 1,
    parseStatus: 'FAILED',
    chunkCount: 0,
    fileSize: '1.1 MB',
    updatedAt: '2026-08-17 18:05',
    errorMessage: '文档中包含无法解析的嵌入对象'
  }
]);

export const visibilityOptions = [
  { label: '项目成员可见', value: 'PROJECT' },
  { label: '负责人和管理员可见', value: 'MANAGERS' },
  { label: '仅创建者可见', value: 'PRIVATE' }
] as const;

export const documentTypeOptions = [
  { label: '标准用例', value: 'STANDARD_CASE' },
  { label: '测试流程', value: 'TEST_PROCESS' },
  { label: '操作指南', value: 'OPERATION_GUIDE' },
  { label: '系统设计', value: 'SYSTEM_DESIGN' },
  { label: '需求文档', value: 'REQUIREMENT' },
  { label: '接口文档', value: 'API_DOCUMENT' },
  { label: '缺陷经验', value: 'DEFECT_EXPERIENCE' },
  { label: '其他', value: 'OTHER' }
] as const;

export function bindDemoDataToProject(projectId: number) {
  knowledgeBases.value.forEach(item => {
    if (item.projectId === 0) item.projectId = projectId;
  });
  knowledgeDocuments.value.forEach(item => {
    if (item.projectId === 0) item.projectId = projectId;
  });
}

export function nextKnowledgeId(records: Array<{ id: number }>) {
  return Math.max(0, ...records.map(item => item.id)) + 1;
}

export function knowledgeNowText() {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
