import { getServiceBaseURL } from '@/utils/service';
import { request } from '../request';
import { getAuthorization } from '../request/shared';

const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
const { baseURL } = getServiceBaseURL(import.meta.env, isHttpProxy);

/**
 * 解析并分发一个完整的 SSE 事件块。
 * 一个事件块形如：event: delta\ndata: {"content":"..."}
 */
function dispatchKnowledgeChatSseBlock(block: string, handlers: Api.KnowledgeManage.KnowledgeChatStreamHandlers) {
  let eventName = '';
  const dataLines: string[] = [];

  block.split(/\r?\n/).forEach(line => {
    if (line.startsWith('event:')) eventName = line.slice('event:'.length).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart());
  });

  if (!eventName || !dataLines.length) return;

  const data = JSON.parse(dataLines.join('\n')) as unknown;
  if (eventName === 'status') {
    handlers.onStatus?.(data as Api.KnowledgeManage.KnowledgeChatStreamStatus);
  } else if (eventName === 'delta') {
    handlers.onDelta?.(data as Api.KnowledgeManage.KnowledgeChatStreamDelta);
  } else if (eventName === 'citations') {
    handlers.onCitations?.(data as Api.KnowledgeManage.KnowledgeChatStreamCitations);
  } else if (eventName === 'done') {
    handlers.onDone?.(data as Api.KnowledgeManage.KnowledgeChatSendResult);
  } else if (eventName === 'error') {
    handlers.onError?.(data as Api.KnowledgeManage.KnowledgeChatStreamError);
  }
}

/** 分页查询项目知识库。 */
export function fetchGetKnowledgeBaseList(projectId: number, params: Api.KnowledgeManage.KnowledgeBaseSearchParams) {
  return request<Api.KnowledgeManage.KnowledgeBaseList>({
    url: `/knowledge_bases/${projectId}/bases`,
    method: 'get',
    params
  });
}

/** 查询知识库表单可选的已启用模型。 */
export function fetchGetKnowledgeModelOptions(taskType: Api.KnowledgeManage.ModelTaskType) {
  return request<Api.KnowledgeManage.ModelOption[]>({
    url: '/knowledge_bases/model-options',
    method: 'get',
    params: { taskType }
  });
}

/** 创建项目知识库。 */
export function fetchCreateKnowledgeBase(projectId: number, data: Api.KnowledgeManage.KnowledgeBaseCreateParams) {
  return request<Api.KnowledgeManage.KnowledgeBase>({
    url: `/knowledge_bases/${projectId}/bases`,
    method: 'post',
    data
  });
}

/** 编辑项目知识库。 */
export function fetchUpdateKnowledgeBase(
  projectId: number,
  knowledgeBaseId: number,
  data: Api.KnowledgeManage.KnowledgeBaseUpdateParams
) {
  return request<Api.KnowledgeManage.KnowledgeBase>({
    url: `/knowledge_bases/${projectId}/bases/${knowledgeBaseId}`,
    method: 'put',
    data
  });
}

/** 删除项目知识库。 */
export function fetchDeleteKnowledgeBase(projectId: number, knowledgeBaseId: number) {
  return request<null>({
    url: `/knowledge_bases/${projectId}/bases/${knowledgeBaseId}`,
    method: 'delete'
  });
}

/** 分页查询指定知识库中的文档。 */
export function fetchGetKnowledgeDocumentList(
  projectId: number,
  knowledgeBaseId: number,
  params: Api.KnowledgeManage.KnowledgeDocumentSearchParams
) {
  return request<Api.KnowledgeManage.KnowledgeDocumentList>({
    url: `/knowledge-document/${projectId}/bases/${knowledgeBaseId}/documents`,
    method: 'get',
    params: {
      current: params.current,
      size: params.size,
      keyword: params.keyword,
      document_type: params.documentType,
      parse_status: params.parseStatus,
      module_id: params.moduleId
    }
  });
}

/** 上传文件及文档业务信息。 */
export function fetchUploadKnowledgeDocument(
  projectId: number,
  knowledgeBaseId: number,
  params: Api.KnowledgeManage.KnowledgeDocumentUploadParams
) {
  const formData = new FormData();
  formData.append('file', params.file);
  formData.append('document_type', params.documentType);
  formData.append('metadata', JSON.stringify(params.metadata ?? {}));

  if (params.title) formData.append('title', params.title);
  if (params.moduleId) formData.append('module_id', String(params.moduleId));

  return request<Api.KnowledgeManage.KnowledgeDocument>({
    url: `/knowledge-document/${projectId}/bases/${knowledgeBaseId}/documents`,
    method: 'post',
    data: formData
  });
}

/** 提交首次索引、重新索引或失败重试任务。 */
export function fetchIndexKnowledgeDocument(projectId: number, knowledgeBaseId: number, documentId: number) {
  return request<Api.KnowledgeManage.KnowledgeDocument>({
    url: `/knowledge-document/${projectId}/bases/${knowledgeBaseId}/documents/${documentId}/index`,
    method: 'post'
  });
}

/** 删除知识文档；后端同时清理检索切片并异步删除原始存储文件。 */
export function fetchDeleteKnowledgeDocument(projectId: number, knowledgeBaseId: number, documentId: number) {
  return request<null>({
    url: `/knowledge-document/${projectId}/bases/${knowledgeBaseId}/documents/${documentId}`,
    method: 'delete'
  });
}

/** 创建一个属于当前登录用户的知识问答会话。 */
export function fetchCreateKnowledgeChatSession(
  projectId: number,
  knowledgeBaseId: number,
  data: Api.KnowledgeManage.KnowledgeChatSessionCreateParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatSession>({
    url: `/knowledge-chat/${projectId}/bases/${knowledgeBaseId}/sessions`,
    method: 'post',
    data
  });
}

/** 分页查询当前用户在指定知识库中的会话。 */
export function fetchGetKnowledgeChatSessions(
  projectId: number,
  knowledgeBaseId: number,
  params: Api.KnowledgeManage.KnowledgeChatSessionSearchParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatSessionList>({
    url: `/knowledge-chat/${projectId}/bases/${knowledgeBaseId}/sessions`,
    method: 'get',
    params
  });
}

/** 修改会话标题或归档状态。 */
export function fetchUpdateKnowledgeChatSession(
  sessionId: number,
  data: Api.KnowledgeManage.KnowledgeChatSessionUpdateParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatSession>({
    url: `/knowledge-chat/sessions/${sessionId}`,
    method: 'patch',
    data
  });
}

/** 软删除当前用户自己的会话。 */
export function fetchDeleteKnowledgeChatSession(sessionId: number) {
  return request<null>({
    url: `/knowledge-chat/sessions/${sessionId}`,
    method: 'delete'
  });
}

/** 使用消息 ID 游标加载会话历史。 */
export function fetchGetKnowledgeChatMessages(
  sessionId: number,
  params: Api.KnowledgeManage.KnowledgeChatMessageCursorParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatMessageCursor>({
    url: `/knowledge-chat/sessions/${sessionId}/messages`,
    method: 'get',
    params
  });
}

/** 使用独立审计权限分页查看项目内所有用户的知识问答会话。 */
export function fetchGetKnowledgeChatAuditSessions(
  projectId: number,
  params: Api.KnowledgeManage.KnowledgeChatAuditSearchParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatSessionList>({
    url: `/knowledge-chat/audit/${projectId}/sessions`,
    method: 'get',
    params
  });
}

/** 使用独立审计权限读取指定会话消息，不复用普通用户的会话所有权接口。 */
export function fetchGetKnowledgeChatAuditMessages(
  projectId: number,
  sessionId: number,
  params: Api.KnowledgeManage.KnowledgeChatMessageCursorParams
) {
  return request<Api.KnowledgeManage.KnowledgeChatMessageCursor>({
    url: `/knowledge-chat/audit/${projectId}/sessions/${sessionId}/messages`,
    method: 'get',
    params
  });
}

/**
 * 在指定会话中发送问题，并实时消费后端返回的 SSE 事件。
 * 浏览器 Axios 不会暴露逐块响应，因此这里使用原生 fetch + ReadableStream。
 */
export async function fetchSendKnowledgeChatMessage(
  sessionId: number,
  data: Api.KnowledgeManage.KnowledgeChatParams,
  handlers: Api.KnowledgeManage.KnowledgeChatStreamHandlers
) {
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Content-Type': 'application/json'
  };
  const authorization = getAuthorization();
  if (authorization) headers.Authorization = authorization;

  const response = await fetch(`${baseURL}/knowledge-chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query: data.query,
      top_k: data.topK,
      module_id: data.moduleId,
      document_types: data.documentTypes
    })
  });

  // 权限依赖等异常可能在 StreamingResponse 创建前发生，此时仍是普通 HTTP 错误。
  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as { msg?: string } | null;
    throw new Error(errorBody?.msg || `知识问答请求失败（HTTP ${response.status}）`);
  }

  if (!response.body) throw new Error('浏览器未提供流式响应正文');

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    // 网络分块和 SSE 事件边界没有对应关系：一次 read() 可能只有半个事件，
    // 也可能同时包含多个事件，所以必须把不完整内容保留在 buffer 中。
    let boundary = buffer.search(/\r?\n\r?\n/);
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? '\n\n';
      buffer = buffer.slice(boundary + separator.length);
      if (block.trim()) dispatchKnowledgeChatSseBlock(block, handlers);
      boundary = buffer.search(/\r?\n\r?\n/);
    }

    if (done) break;
  }

  // 正常情况下后端事件都以空行结尾；这里兼容连接关闭前剩余的最后一个事件。
  if (buffer.trim()) dispatchKnowledgeChatSseBlock(buffer, handlers);
}

/**
 * 读取一篇经过后端数据权限校验的知识文档原文件。
 * 使用原生 fetch 是因为响应为二进制文件，而不是项目统一的 ApiResult JSON。
 */
export async function fetchPreviewKnowledgeDocument(projectId: number, knowledgeBaseId: number, documentId: number) {
  const headers: Record<string, string> = {};
  const authorization = getAuthorization();
  if (authorization) headers.Authorization = authorization;

  const response = await fetch(
    `${baseURL}/knowledge-document/${projectId}/bases/${knowledgeBaseId}/documents/${documentId}/preview`,
    { headers }
  );

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as { msg?: string } | null;
    throw new Error(errorBody?.msg || `文档预览失败（HTTP ${response.status}）`);
  }

  const disposition = response.headers.get('Content-Disposition') || '';
  const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  let filename: string | null = null;
  if (encodedFilename) {
    try {
      filename = decodeURIComponent(encodedFilename);
    } catch {
      // 非法响应头不影响文件预览，下载时再使用文档标题兜底。
    }
  }

  return {
    blob: await response.blob(),
    filename
  };
}
