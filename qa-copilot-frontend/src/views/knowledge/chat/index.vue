<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import {
  fetchCreateKnowledgeChatSession,
  fetchDeleteKnowledgeChatSession,
  fetchGetKnowledgeBaseList,
  fetchGetKnowledgeChatAuditMessages,
  fetchGetKnowledgeChatAuditSessions,
  fetchGetKnowledgeChatMessages,
  fetchGetKnowledgeChatSessions,
  fetchGetProjectList,
  fetchGetProjectModules,
  fetchSendKnowledgeChatMessage,
  fetchUpdateKnowledgeChatSession
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import KnowledgeDocumentPreviewDialog from './components/knowledge-document-preview-dialog.vue';

defineOptions({ name: 'KnowledgeChat' });

type MessageContentSegment = {
  key: string;
  type: 'text' | 'citation';
  content: string;
  sourceNumber: number | null;
};

const authStore = useAuthStore();
const loading = ref(false);
const sessionLoading = ref(false);
const historyLoading = ref(false);
const answering = ref(false);
const streamStageMessage = ref('正在生成回答');
const activeProjectId = ref<number | null>(null);
const activeKnowledgeBaseId = ref<number | null>(null);
const activeSessionId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const knowledgeBases = ref<Api.KnowledgeManage.KnowledgeBase[]>([]);
const modules = ref<Api.ProjectManage.ProjectModule[]>([]);
const sessions = ref<Api.KnowledgeManage.KnowledgeChatSession[]>([]);
const messages = ref<Api.KnowledgeManage.KnowledgeChatMessage[]>([]);
const question = ref('');
const selectedModuleId = ref<number | null>(null);
const selectedDocumentTypes = ref<Api.KnowledgeManage.KnowledgeDocumentType[]>([]);
const hasMoreMessages = ref(false);
const nextMessageCursor = ref<number | null>(null);
const messageListRef = ref<HTMLElement>();
const previewDialogRef = ref<InstanceType<typeof KnowledgeDocumentPreviewDialog>>();
const highlightedCitationKey = ref('');
const auditDrawerVisible = ref(false);
const auditLoading = ref(false);
const auditMessageLoading = ref(false);
const auditSessions = ref<Api.KnowledgeManage.KnowledgeChatSession[]>([]);
const auditMessages = ref<Api.KnowledgeManage.KnowledgeChatMessage[]>([]);
const auditTotal = ref(0);
const auditSession = ref<Api.KnowledgeManage.KnowledgeChatSession | null>(null);
const auditBeforeId = ref<number | undefined>();
const auditHasMore = ref(false);
const auditStatus = ref<Api.KnowledgeManage.KnowledgeChatSessionStatus | undefined>();
const auditUserId = ref<number | undefined>();
let citationHighlightTimer: number | undefined;
let pendingMessagePollTimer: number | undefined;
let pendingMessagePollSessionId: number | null = null;

const PENDING_MESSAGE_POLL_INTERVAL_MS = 2000;
const PENDING_MESSAGE_POLL_MAX_ATTEMPTS = 90;

const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const knowledgeBaseOptions = computed(() => knowledgeBases.value.filter(item => item.enabled));
const documentTypeOptions: Array<{
  label: string;
  value: Api.KnowledgeManage.KnowledgeDocumentType;
}> = [
  { label: '标准用例', value: 'STANDARD_CASE' },
  { label: '测试流程', value: 'TEST_PROCESS' },
  { label: '操作指南', value: 'OPERATION_GUIDE' },
  { label: '系统设计', value: 'SYSTEM_DESIGN' },
  { label: '需求文档', value: 'REQUIREMENT' },
  { label: 'API 文档', value: 'API_DOCUMENT' },
  { label: '缺陷经验', value: 'DEFECT_EXPERIENCE' },
  { label: '其他', value: 'OTHER' }
];
const activeSession = computed(() => sessions.value.find(item => item.id === activeSessionId.value) ?? null);
const moduleOptions = computed(() => {
  const result: Array<{ label: string; value: number }> = [];

  function appendOptions(items: Api.ProjectManage.ProjectModule[], depth = 0) {
    items.forEach(item => {
      result.push({ label: `${'　'.repeat(depth)}${item.name}`, value: item.id });
      appendOptions(item.children, depth + 1);
    });
  }

  appendOptions(modules.value);
  return result;
});
const canChat = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('knowledge:chat:use');
});
const canAudit = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('knowledge:chat:audit');
});

/**
 * 打开项目级只读审计面板。
 * 它调用独立审计权限接口，不会绕过普通用户只能读取自己会话的所有权规则。
 */
async function openAuditDrawer() {
  if (!activeProjectId.value) return;
  auditSession.value = null;
  auditMessages.value = [];
  auditDrawerVisible.value = true;
  await loadAuditSessions();
}

async function loadAuditSessions() {
  if (!activeProjectId.value) return;
  auditLoading.value = true;
  const { data, error } = await fetchGetKnowledgeChatAuditSessions(activeProjectId.value, {
    current: 1,
    size: 100,
    knowledgeBaseId: activeKnowledgeBaseId.value ?? undefined,
    userId: auditUserId.value,
    status: auditStatus.value
  });
  auditLoading.value = false;
  if (error) return;
  auditSessions.value = data.records;
  auditTotal.value = data.total;
}

async function selectAuditSession(session: Api.KnowledgeManage.KnowledgeChatSession) {
  auditSession.value = session;
  auditMessages.value = [];
  auditBeforeId.value = undefined;
  auditHasMore.value = false;
  await loadAuditMessages();
}

async function loadAuditMessages(loadEarlier = false) {
  if (!activeProjectId.value || !auditSession.value) return;
  auditMessageLoading.value = true;
  const { data, error } = await fetchGetKnowledgeChatAuditMessages(activeProjectId.value, auditSession.value.id, {
    limit: 100,
    beforeId: loadEarlier ? auditBeforeId.value : undefined
  });
  auditMessageLoading.value = false;
  if (error) return;
  auditMessages.value = loadEarlier ? [...data.records, ...auditMessages.value] : data.records;
  auditHasMore.value = data.hasMore;
  auditBeforeId.value = data.nextCursor ?? undefined;
}
const sendDisabled = computed(() => {
  return (
    !canChat.value ||
    !question.value.trim() ||
    !activeKnowledgeBaseId.value ||
    answering.value ||
    activeSession.value?.status === 'ARCHIVED'
  );
});
const composerPlaceholder = computed(() => {
  if (!activeKnowledgeBaseId.value) return '请先选择知识库';
  if (activeSession.value?.status === 'ARCHIVED') return '当前会话已归档，请新建会话后继续提问';
  return '输入关于当前项目测试资料的问题…';
});

function resetConversation() {
  stopPendingMessagePolling();
  sessions.value = [];
  activeSessionId.value = null;
  messages.value = [];
  hasMoreMessages.value = false;
  nextMessageCursor.value = null;
}

async function getProjects() {
  loading.value = true;
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  loading.value = false;
  if (error) return;

  projects.value = data.records;
  activeProjectId.value = projects.value[0]?.id ?? null;
  await loadProjectResources();
}

async function loadProjectResources() {
  knowledgeBases.value = [];
  modules.value = [];
  activeKnowledgeBaseId.value = null;
  selectedModuleId.value = null;
  selectedDocumentTypes.value = [];
  resetConversation();

  if (!activeProjectId.value) return;

  loading.value = true;
  const [knowledgeBaseResult, moduleResult] = await Promise.all([
    fetchGetKnowledgeBaseList(activeProjectId.value, { current: 1, size: 100, keyword: '', enabled: true }),
    fetchGetProjectModules(activeProjectId.value, { keyword: '' })
  ]);
  loading.value = false;

  if (!knowledgeBaseResult.error) {
    knowledgeBases.value = knowledgeBaseResult.data.records;
    activeKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? null;
  }
  if (!moduleResult.error) modules.value = moduleResult.data;

  await loadSessions();
}

async function handleProjectChange() {
  await loadProjectResources();
}

async function handleKnowledgeBaseChange() {
  resetConversation();
  await loadSessions();
}

async function loadSessions(preferredSessionId?: number) {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) {
    resetConversation();
    return;
  }

  sessionLoading.value = true;
  const { data, error } = await fetchGetKnowledgeChatSessions(activeProjectId.value, activeKnowledgeBaseId.value, {
    current: 1,
    size: 100
  });
  sessionLoading.value = false;
  if (error) return;

  sessions.value = data.records;
  const selectedId = preferredSessionId ?? activeSessionId.value;
  const selectedSession = sessions.value.find(item => item.id === selectedId);
  const defaultSession = selectedSession ?? sessions.value.find(item => item.status === 'ACTIVE') ?? sessions.value[0];

  activeSessionId.value = defaultSession?.id ?? null;
  if (activeSessionId.value) {
    await loadMessages(true);
  } else {
    messages.value = [];
  }
}

async function selectSession(sessionId: number) {
  if (sessionId === activeSessionId.value) return;
  stopPendingMessagePolling();
  answering.value = false;
  streamStageMessage.value = '正在生成回答';
  activeSessionId.value = sessionId;
  await loadMessages(true);
}

/** 停止刷新正在生成的 AI 消息。 */
function stopPendingMessagePolling() {
  if (pendingMessagePollTimer !== undefined) {
    window.clearTimeout(pendingMessagePollTimer);
    pendingMessagePollTimer = undefined;
  }
  pendingMessagePollSessionId = null;
}

/**
 * 后端已经保存 ASSISTANT/PENDING，但本次 POST 可能因浏览器超时而断开。
 * 此时定时查询会话消息；后端完成后，数据库中的同一条消息会变为
 * SUCCESS 或 FAILED，当前页面便能自动显示最终状态，无需切换页面。
 */
function startPendingMessagePolling(sessionId: number, attempt = 0) {
  stopPendingMessagePolling();

  if (attempt >= PENDING_MESSAGE_POLL_MAX_ATTEMPTS) {
    answering.value = false;
    window.$message?.warning('回答仍在后台生成，可稍后重新进入会话查看');
    return;
  }

  pendingMessagePollSessionId = sessionId;
  pendingMessagePollTimer = window.setTimeout(async () => {
    pendingMessagePollTimer = undefined;

    // 用户切换了会话或页面后，旧会话的轮询不能覆盖新会话消息。
    if (activeSessionId.value !== sessionId || pendingMessagePollSessionId !== sessionId) return;

    const { data, error } = await fetchGetKnowledgeChatMessages(sessionId, { limit: 20 });
    if (activeSessionId.value !== sessionId || pendingMessagePollSessionId !== sessionId) return;

    if (error) {
      startPendingMessagePolling(sessionId, attempt + 1);
      return;
    }

    messages.value = data.records;
    hasMoreMessages.value = data.hasMore;
    nextMessageCursor.value = data.nextCursor;

    if (data.records.some(message => message.status === 'PENDING')) {
      answering.value = true;
      streamStageMessage.value = '正在等待后台完成回答';
      startPendingMessagePolling(sessionId, attempt + 1);
      return;
    }

    stopPendingMessagePolling();
    answering.value = false;
    await scrollToBottom();
  }, PENDING_MESSAGE_POLL_INTERVAL_MS);
}

/**
 * 用第一次提问为默认会话命名。
 * 会话标题与 AI 是否生成成功无关，因此不能等问答 POST 成功后才更新。
 */
async function autoRenameSession(sessionId: number, firstQuestion: string) {
  const session = sessions.value.find(item => item.id === sessionId);
  if (!session || session.title !== '新会话') return;

  const title = firstQuestion.trim().slice(0, 50);
  if (!title) return;

  const { data, error } = await fetchUpdateKnowledgeChatSession(sessionId, { title });
  if (error) return;

  sessions.value = [data, ...sessions.value.filter(item => item.id !== sessionId)];
}

async function loadMessages(reset = true) {
  if (!activeSessionId.value) return;

  historyLoading.value = true;
  const { data, error } = await fetchGetKnowledgeChatMessages(activeSessionId.value, {
    beforeId: reset ? undefined : (nextMessageCursor.value ?? undefined),
    limit: 20
  });
  historyLoading.value = false;
  if (error) return;

  messages.value = reset ? data.records : [...data.records, ...messages.value];
  hasMoreMessages.value = data.hasMore;
  nextMessageCursor.value = data.nextCursor;

  if (reset) {
    // 兼顾修复旧数据：以前问答 POST 超时后没有执行自动改名，
    // 再次加载会话时可根据当前查到的第一条用户消息补上标题。
    const firstUserMessage = data.records.find(message => message.role === 'USER');
    if (firstUserMessage) await autoRenameSession(activeSessionId.value, firstUserMessage.content);

    if (data.records.some(message => message.status === 'PENDING')) {
      answering.value = true;
      startPendingMessagePolling(activeSessionId.value);
    } else if (pendingMessagePollSessionId === activeSessionId.value) {
      stopPendingMessagePolling();
      answering.value = false;
    }
    await scrollToBottom();
  }
}

async function createSession(title = '新会话') {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) {
    window.$message?.warning('请先选择项目和知识库');
    return null;
  }

  const { data, error } = await fetchCreateKnowledgeChatSession(activeProjectId.value, activeKnowledgeBaseId.value, {
    title
  });
  if (error) return null;

  sessions.value = [data, ...sessions.value.filter(item => item.id !== data.id)];
  activeSessionId.value = data.id;
  messages.value = [];
  hasMoreMessages.value = false;
  nextMessageCursor.value = null;
  return data;
}

async function handleCreateSession() {
  const session = await createSession();
  if (session) window.$message?.success('会话创建成功');
}

async function renameSession(session: Api.KnowledgeManage.KnowledgeChatSession) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话标题', '重命名会话', {
      inputValue: session.title,
      inputPattern: /\S+/,
      inputErrorMessage: '会话标题不能为空',
      confirmButtonText: '保存',
      cancelButtonText: '取消'
    });
    const title = value.trim();
    const { data, error } = await fetchUpdateKnowledgeChatSession(session.id, { title });
    if (error) return;
    sessions.value = sessions.value.map(item => (item.id === data.id ? data : item));
    window.$message?.success('会话标题已更新');
  } catch {
    // Element Plus 在用户取消输入框时会 reject，无需展示错误。
  }
}

async function toggleSessionArchive(session: Api.KnowledgeManage.KnowledgeChatSession) {
  const status: Api.KnowledgeManage.KnowledgeChatSessionStatus = session.status === 'ACTIVE' ? 'ARCHIVED' : 'ACTIVE';
  const { data, error } = await fetchUpdateKnowledgeChatSession(session.id, { status });
  if (error) return;

  sessions.value = sessions.value.map(item => (item.id === data.id ? data : item));
  window.$message?.success(status === 'ARCHIVED' ? '会话已归档' : '会话已恢复');
}

async function deleteSession(session: Api.KnowledgeManage.KnowledgeChatSession) {
  try {
    await ElMessageBox.confirm(`确认删除会话“${session.title}”吗？`, '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    });
  } catch {
    return;
  }

  const { error } = await fetchDeleteKnowledgeChatSession(session.id);
  if (error) return;

  sessions.value = sessions.value.filter(item => item.id !== session.id);
  if (activeSessionId.value === session.id) {
    const nextSession = sessions.value.find(item => item.status === 'ACTIVE') ?? sessions.value[0];
    activeSessionId.value = nextSession?.id ?? null;
    if (activeSessionId.value) await loadMessages(true);
    else messages.value = [];
  }
  window.$message?.success('会话已删除');
}

async function scrollToBottom() {
  await nextTick();
  if (messageListRef.value) messageListRef.value.scrollTop = messageListRef.value.scrollHeight;
}

async function sendQuestion() {
  const content = question.value.trim();
  if (!content || answering.value) return;
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) {
    window.$message?.warning('请先选择知识库');
    return;
  }

  let session = activeSession.value;
  if (!session) {
    session = await createSession(content.slice(0, 50));
    if (!session) return;
  }
  if (session.status === 'ARCHIVED') {
    window.$message?.warning('归档会话不能继续发送消息');
    return;
  }

  // 只有默认标题的空会话，才使用第一个问题自动命名。
  // 已经重命名的会话或后续问题都不会覆盖现有标题。
  const shouldAutoRename = session.title === '新会话' && messages.value.length === 0;
  const messageIdsBeforeSend = new Set(messages.value.map(message => message.id));
  const temporaryMessageId = -Date.now();
  const temporaryAssistantMessageId = temporaryMessageId - 1;
  const temporaryCreatedAt = new Date().toISOString();
  const temporaryMessage: Api.KnowledgeManage.KnowledgeChatMessage = {
    id: temporaryMessageId,
    sessionId: session.id,
    role: 'USER',
    content,
    citations: [],
    modelId: null,
    promptTemplateId: null,
    status: 'SUCCESS',
    tokenCount: 0,
    errorMessage: null,
    createdAt: temporaryCreatedAt
  };
  const temporaryAssistantMessage: Api.KnowledgeManage.KnowledgeChatMessage = {
    id: temporaryAssistantMessageId,
    sessionId: session.id,
    role: 'ASSISTANT',
    content: '',
    citations: [],
    modelId: null,
    promptTemplateId: null,
    status: 'PENDING',
    tokenCount: 0,
    errorMessage: null,
    createdAt: temporaryCreatedAt
  };

  messages.value.push(temporaryMessage, temporaryAssistantMessage);
  question.value = '';
  answering.value = true;
  streamStageMessage.value = '正在提交问题';
  await scrollToBottom();

  // 标题取决于第一次提问，不依赖后面耗时较长的 AI 生成结果。
  // 即使问答请求超时或模型生成失败，会话也不会一直显示“新会话”。
  if (shouldAutoRename) await autoRenameSession(session.id, content);

  // 回调中的赋值发生在 fetch 读取流的过程中。使用可变对象保存结果，
  // 让 TypeScript 明确知道 await 结束后这两个字段仍可能已经被回调更新。
  const streamState: {
    completedResult: Api.KnowledgeManage.KnowledgeChatSendResult | null;
    streamError: Api.KnowledgeManage.KnowledgeChatStreamError | null;
  } = {
    completedResult: null,
    streamError: null
  };
  let requestErrorMessage = '';

  try {
    await fetchSendKnowledgeChatMessage(
      session.id,
      {
        query: content,
        topK: 5,
        moduleId: selectedModuleId.value ?? undefined,
        documentTypes: selectedDocumentTypes.value
      },
      {
        onStatus(data) {
          if (activeSessionId.value === session.id) streamStageMessage.value = data.message;
        },
        onDelta(data) {
          if (activeSessionId.value !== session.id) return;
          const assistant = messages.value.find(message => message.id === temporaryAssistantMessageId);
          if (!assistant) return;

          // 每个 DELTA 只包含本次新增文字，需要依次追加才能得到完整回答。
          assistant.content += data.content;
          void scrollToBottom();
        },
        onCitations(data) {
          if (activeSessionId.value !== session.id) return;
          const assistant = messages.value.find(message => message.id === temporaryAssistantMessageId);
          if (assistant) assistant.citations = data.citations;
        },
        onDone(data) {
          streamState.completedResult = data;
        },
        onError(data) {
          streamState.streamError = data;
        }
      }
    );
  } catch (error) {
    requestErrorMessage = error instanceof Error ? error.message : '知识问答连接异常';
  }

  const completedResult = streamState.completedResult;
  if (completedResult) {
    stopPendingMessagePolling();

    // 用户可能在生成期间切换了会话。只有仍停留在原会话时才替换消息区域，
    // 但左侧会话的最近消息时间无论如何都需要更新。
    if (activeSessionId.value === session.id) {
      messages.value = messages.value.filter(
        message => message.id !== temporaryMessageId && message.id !== temporaryAssistantMessageId
      );
      messages.value.push(completedResult.userMessage, completedResult.assistantMessage);
    }

    const updatedSession = sessions.value.find(item => item.id === session.id) ?? session;
    updatedSession.lastMessageAt = completedResult.assistantMessage.createdAt;

    sessions.value = [updatedSession, ...sessions.value.filter(item => item.id !== session.id)];
  } else if (activeSessionId.value === session.id) {
    // ERROR 事件或网络断开后重新查询数据库：如果后端已经保存了 FAILED 或
    // PENDING，使用真实消息替换临时消息；PENDING 会自动启动轮询恢复。
    await loadMessages(true);

    const questionWasPersisted = messages.value.some(
      message => !messageIdsBeforeSend.has(message.id) && message.role === 'USER' && message.content === content
    );
    if (!questionWasPersisted) question.value = content;

    const errorMessage = streamState.streamError?.message || requestErrorMessage;
    if (errorMessage) window.$message?.error(errorMessage);
  }

  if (activeSessionId.value === session.id) {
    answering.value = messages.value.some(message => message.status === 'PENDING');
    if (!answering.value) streamStageMessage.value = '正在生成回答';
    await scrollToBottom();
  }
}

function formatCitationLocation(citation: Api.KnowledgeManage.KnowledgeCitation) {
  const parts: string[] = [];
  if (citation.pageNo !== null) parts.push(`第 ${citation.pageNo} 页`);
  if (citation.sectionTitle) parts.push(citation.sectionTitle);
  if (citation.moduleName) parts.push(`模块：${citation.moduleName}`);
  return parts.join(' · ') || `切片 ${citation.chunkIndex + 1}`;
}

/**
 * 模型仍然输出 [资料N]，便于后端解析引用。
 * 前端在展示时把它拆成普通文本和可点击引用角标。
 */
function parseMessageContent(message: Api.KnowledgeManage.KnowledgeChatMessage): MessageContentSegment[] {
  if (message.role !== 'ASSISTANT') {
    return [{ key: 'text-0', type: 'text', content: message.content, sourceNumber: null }];
  }

  const segments: MessageContentSegment[] = [];
  const availableSourceNumbers = new Set(message.citations.map(citation => citation.sourceNumber));
  const referencePattern = /\[资料(\d+)]/g;
  let lastIndex = 0;
  let segmentIndex = 0;

  for (const match of message.content.matchAll(referencePattern)) {
    const matchIndex = match.index;
    if (matchIndex > lastIndex) {
      segments.push({
        key: `text-${segmentIndex}`,
        type: 'text',
        content: message.content.slice(lastIndex, matchIndex),
        sourceNumber: null
      });
      segmentIndex += 1;
    }

    const sourceNumber = Number(match[1]);
    if (availableSourceNumbers.has(sourceNumber)) {
      segments.push({
        key: `citation-${segmentIndex}`,
        type: 'citation',
        content: match[0],
        sourceNumber
      });
    } else {
      // 模型如果生成了不存在的资料编号，不渲染成可点击链接。
      segments.push({
        key: `text-${segmentIndex}`,
        type: 'text',
        content: match[0],
        sourceNumber: null
      });
    }
    segmentIndex += 1;
    lastIndex = matchIndex + match[0].length;
  }

  if (lastIndex < message.content.length) {
    segments.push({
      key: `text-${segmentIndex}`,
      type: 'text',
      content: message.content.slice(lastIndex),
      sourceNumber: null
    });
  }

  return segments.length ? segments : [{ key: 'text-0', type: 'text', content: message.content, sourceNumber: null }];
}

function getCitationReferenceTitle(message: Api.KnowledgeManage.KnowledgeChatMessage, sourceNumber: number | null) {
  const citation = message.citations.find(item => item.sourceNumber === sourceNumber);
  return citation ? `查看来源：${citation.documentTitle}` : '查看引用来源';
}

function scrollToCitation(messageId: number, sourceNumber: number | null) {
  if (sourceNumber === null) return;

  const citationKey = `${messageId}-${sourceNumber}`;
  const citationElement = document.getElementById(`citation-${citationKey}`);
  if (!citationElement) return;

  highlightedCitationKey.value = citationKey;
  citationElement.scrollIntoView({ behavior: 'smooth', block: 'center' });

  if (citationHighlightTimer !== undefined) window.clearTimeout(citationHighlightTimer);
  citationHighlightTimer = window.setTimeout(() => {
    if (highlightedCitationKey.value === citationKey) highlightedCitationKey.value = '';
  }, 1800);
}

async function previewCitation(citation: Api.KnowledgeManage.KnowledgeCitation) {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) return;
  await previewDialogRef.value?.open(citation, activeProjectId.value, activeKnowledgeBaseId.value);
}

function formatSessionTime(value: string | null) {
  if (!value) return '尚未开始';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

onBeforeUnmount(() => {
  if (citationHighlightTimer !== undefined) window.clearTimeout(citationHighlightTimer);
  stopPendingMessagePolling();
});

getProjects();
</script>

<template>
  <div class="knowledge-chat-page">
    <aside class="chat-side-panel">
      <div class="chat-panel-title">
        <span><SvgIcon icon="mdi:tune-variant" /></span>
        <div>
          <strong>检索范围</strong>
          <small>缩小范围可提高回答准确度</small>
        </div>
      </div>

      <ElForm class="scope-form" label-position="top">
        <ElFormItem label="项目">
          <ElSelect v-model="activeProjectId" class="w-full" :loading="loading" @change="handleProjectChange">
            <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="知识库">
          <ElSelect
            v-model="activeKnowledgeBaseId"
            class="w-full"
            placeholder="选择知识库"
            @change="handleKnowledgeBaseChange"
          >
            <ElOption v-for="item in knowledgeBaseOptions" :key="item.id" :label="item.name" :value="item.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="功能模块（可选）">
          <ElSelect v-model="selectedModuleId" clearable class="w-full" placeholder="全部模块">
            <ElOption v-for="item in moduleOptions" :key="item.value" :label="item.label" :value="item.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="知识类型（可选）">
          <ElSelect
            v-model="selectedDocumentTypes"
            multiple
            clearable
            collapse-tags
            collapse-tags-tooltip
            class="w-full"
            placeholder="全部类型"
          >
            <ElOption v-for="item in documentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </ElSelect>
        </ElFormItem>
      </ElForm>

      <div class="session-heading">
        <div>
          <strong>会话记录</strong>
          <small>{{ sessions.length }} 个会话</small>
        </div>
        <ElButton
          circle
          size="small"
          type="primary"
          title="新建会话"
          :disabled="!canChat || !activeKnowledgeBaseId"
          @click="handleCreateSession"
        >
          <template #icon><icon-mdi-plus /></template>
        </ElButton>
      </div>

      <div v-loading="sessionLoading" class="session-list">
        <div v-if="!sessionLoading && !sessions.length" class="session-empty">暂无会话，点击右上角新建</div>
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ 'is-active': session.id === activeSessionId, 'is-archived': session.status === 'ARCHIVED' }"
          role="button"
          tabindex="0"
          @click="selectSession(session.id)"
          @keydown.enter="selectSession(session.id)"
        >
          <span class="session-icon"><SvgIcon icon="mdi:message-text-outline" /></span>
          <span class="session-content">
            <b>{{ session.title }}</b>
            <small>{{ formatSessionTime(session.lastMessageAt || session.createdAt) }}</small>
          </span>
          <span class="session-actions">
            <button type="button" title="重命名" @click.stop="renameSession(session)">
              <SvgIcon icon="mdi:pencil-outline" />
            </button>
            <button
              type="button"
              :title="session.status === 'ACTIVE' ? '归档' : '恢复'"
              @click.stop="toggleSessionArchive(session)"
            >
              <SvgIcon
                :icon="session.status === 'ACTIVE' ? 'mdi:archive-arrow-down-outline' : 'mdi:archive-arrow-up-outline'"
              />
            </button>
            <button type="button" title="删除" @click.stop="deleteSession(session)">
              <SvgIcon icon="mdi:delete-outline" />
            </button>
          </span>
        </div>
      </div>

      <div class="rag-policy">
        <SvgIcon icon="mdi:shield-check-outline" />
        <span>回答必须引用知识来源；证据不足时明确告知，不允许无依据生成。</span>
      </div>
    </aside>

    <section class="chat-main">
      <header class="chat-header">
        <div class="chat-heading">
          <span><SvgIcon icon="mdi:message-text-outline" /></span>
          <div>
            <h2>{{ activeSession?.title || '知识问答' }}</h2>
            <p>
              {{ knowledgeBaseOptions.find(item => item.id === activeKnowledgeBaseId)?.name || '请选择知识库' }}
              <ElTag v-if="activeSession?.status === 'ARCHIVED'" class="ml-2" size="small" type="info">已归档</ElTag>
            </p>
          </div>
        </div>
        <div class="chat-header-actions">
          <ElButton v-if="canAudit" plain @click="openAuditDrawer">
            <template #icon><SvgIcon icon="mdi:shield-search-outline" /></template>
            会话审计
          </ElButton>
          <ElButton type="primary" plain :disabled="!canChat || !activeKnowledgeBaseId" @click="handleCreateSession">
            <template #icon><icon-mdi-plus /></template>
            新建会话
          </ElButton>
        </div>
      </header>

      <div ref="messageListRef" v-loading="historyLoading" class="message-list">
        <div v-if="hasMoreMessages" class="load-more-row">
          <ElButton text :loading="historyLoading" @click="loadMessages(false)">加载更早消息</ElButton>
        </div>

        <div v-if="!messages.length && !historyLoading" class="chat-empty">
          <span><SvgIcon icon="mdi:robot-outline" /></span>
          <h3>{{ activeSession ? '开始这次知识问答' : '创建会话后开始提问' }}</h3>
          <p>我会严格依据当前知识库的文档回答，并展示引用来源。</p>
        </div>

        <div
          v-for="message in messages"
          :key="message.id"
          class="message-row"
          :class="`is-${message.role.toLowerCase()}`"
        >
          <div class="message-avatar">
            <SvgIcon :icon="message.role === 'ASSISTANT' ? 'mdi:robot-outline' : 'mdi:account-outline'" />
          </div>
          <div class="message-body">
            <div v-if="message.status === 'FAILED'" class="message-content is-failed">
              回答生成失败：{{ message.errorMessage || '未知错误' }}
            </div>
            <div v-else-if="message.status === 'PENDING' && !message.content" class="answering-indicator">
              <i />
              <i />
              <i />
              <span>{{ streamStageMessage }}</span>
            </div>
            <div v-else class="message-content">
              <template v-for="segment in parseMessageContent(message)" :key="segment.key">
                <span v-if="segment.type === 'text'">{{ segment.content }}</span>
                <button
                  v-else
                  type="button"
                  class="citation-reference"
                  :title="getCitationReferenceTitle(message, segment.sourceNumber)"
                  @click="scrollToCitation(message.id, segment.sourceNumber)"
                >
                  [{{ segment.sourceNumber }}]
                </button>
              </template>
              <span v-if="message.status === 'PENDING'" class="stream-cursor" aria-hidden="true" />
            </div>

            <div v-if="message.status === 'PENDING' && message.content" class="stream-stage">
              <i />
              <span>{{ streamStageMessage }}</span>
            </div>

            <div v-if="message.citations?.length" class="citation-list">
              <strong>
                <SvgIcon icon="mdi:format-quote-close" />
                引用依据
              </strong>
              <button
                v-for="(citation, index) in message.citations"
                :id="`citation-${message.id}-${citation.sourceNumber}`"
                :key="`${message.id}-${index}`"
                type="button"
                class="citation-card"
                :class="{ 'is-highlighted': highlightedCitationKey === `${message.id}-${citation.sourceNumber}` }"
                title="打开原始文档"
                @click="previewCitation(citation)"
              >
                <span class="citation-index">{{ citation.sourceNumber }}</span>
                <span>
                  <b>{{ citation.documentTitle }}</b>
                  <small>{{ formatCitationLocation(citation) }}</small>
                  <em>{{ citation.content }}</em>
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <footer class="chat-composer">
        <div class="composer-box">
          <ElInput
            v-model="question"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            resize="none"
            :placeholder="composerPlaceholder"
            :disabled="!canChat || !activeKnowledgeBaseId || activeSession?.status === 'ARCHIVED'"
            @keydown.ctrl.enter.prevent="sendQuestion"
          />
          <div class="composer-actions">
            <span>Ctrl + Enter 发送</span>
            <ElButton type="primary" :loading="answering" :disabled="sendDisabled" @click="sendQuestion">
              <template #icon><icon-mdi-send /></template>
              发送
            </ElButton>
          </div>
        </div>
      </footer>
    </section>

    <KnowledgeDocumentPreviewDialog ref="previewDialogRef" />

    <ElDrawer v-model="auditDrawerVisible" title="知识问答会话审计" size="900px">
      <ElAlert
        title="审计接口使用独立权限，只读查看当前项目会话，不改变普通用户只能访问自己会话的规则。"
        type="info"
        :closable="false"
      />
      <div class="audit-filters">
        <ElInputNumber v-model="auditUserId" :min="1" :controls="false" placeholder="用户 ID" />
        <ElSelect v-model="auditStatus" clearable placeholder="全部状态">
          <ElOption label="进行中" value="ACTIVE" />
          <ElOption label="已归档" value="ARCHIVED" />
        </ElSelect>
        <ElButton type="primary" :loading="auditLoading" @click="loadAuditSessions">查询</ElButton>
      </div>
      <div class="audit-layout">
        <section v-loading="auditLoading" class="audit-session-list">
          <div class="audit-count">共 {{ auditTotal }} 个会话</div>
          <button
            v-for="session in auditSessions"
            :key="session.id"
            type="button"
            class="audit-session-item"
            :class="{ 'is-active': auditSession?.id === session.id }"
            @click="selectAuditSession(session)"
          >
            <strong>{{ session.title }}</strong>
            <span>
              {{ session.userName || `用户 #${session.userId}` }} ·
              {{ session.status === 'ACTIVE' ? '进行中' : '已归档' }}
            </span>
            <small>{{ formatSessionTime(session.lastMessageAt || session.createdAt) }}</small>
          </button>
          <ElEmpty v-if="!auditLoading && !auditSessions.length" description="没有符合条件的会话" :image-size="64" />
        </section>
        <section v-loading="auditMessageLoading" class="audit-message-list">
          <ElButton v-if="auditHasMore" text type="primary" @click="loadAuditMessages(true)">加载更早消息</ElButton>
          <article v-for="message in auditMessages" :key="message.id" class="audit-message">
            <header>
              <ElTag :type="message.role === 'USER' ? 'primary' : 'success'" size="small">
                {{ message.role === 'USER' ? '用户' : 'AI' }}
              </ElTag>
              <span>{{ formatSessionTime(message.createdAt) }} · {{ message.tokenCount }} Token</span>
              <ElTag v-if="message.status !== 'SUCCESS'" type="danger" size="small">{{ message.status }}</ElTag>
            </header>
            <p>{{ message.content || message.errorMessage || '无正文' }}</p>
            <small v-if="message.citations.length">引用 {{ message.citations.length }} 条知识证据</small>
          </article>
          <ElEmpty v-if="!auditSession" description="请从左侧选择一个会话" :image-size="72" />
        </section>
      </div>
    </ElDrawer>
  </div>
</template>

<style scoped lang="scss">
.knowledge-chat-page {
  display: grid;
  height: 100%;
  min-height: 620px;
  grid-template-columns: 290px minmax(0, 1fr);
  gap: 12px;
}
.chat-header-actions {
  display: flex;
  gap: 8px;
}
.audit-filters {
  display: grid;
  grid-template-columns: 160px 160px auto;
  gap: 10px;
  margin: 14px 0;
}
.audit-layout {
  display: grid;
  min-height: 560px;
  grid-template-columns: 280px minmax(0, 1fr);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}
.audit-session-list {
  padding: 10px;
  border-right: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-extra-light);
}
.audit-count {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.audit-session-item {
  display: flex;
  width: 100%;
  margin-bottom: 6px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  flex-direction: column;
  gap: 4px;
}
.audit-session-item:hover,
.audit-session-item.is-active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.audit-session-item span,
.audit-session-item small,
.audit-message header span,
.audit-message > small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.audit-message-list {
  padding: 16px;
  overflow: auto;
}
.audit-message {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.audit-message header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.audit-message p {
  margin: 10px 0 4px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.chat-side-panel,
.chat-main {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  box-shadow: 0 8px 24px rgb(0 0 0 / 2%);
}

.chat-side-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  padding: 16px;
}

.chat-panel-title,
.chat-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-panel-title {
  margin-bottom: 14px;
}

.chat-panel-title > span,
.chat-heading > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgb(var(--primary-color) / 9%);
  color: rgb(var(--primary-color));
}

.chat-panel-title > span {
  width: 36px;
  height: 36px;
  font-size: 18px;
}

.chat-panel-title div,
.chat-heading div,
.session-heading div {
  display: flex;
  flex-direction: column;
}

.chat-panel-title strong,
.session-heading strong {
  font-size: 14px;
}

.chat-panel-title small,
.session-heading small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.scope-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.session-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 14px;
}

.session-list {
  min-height: 96px;
  flex: 1;
  overflow: auto;
  margin: 10px -5px 0;
  padding: 0 5px;
}

.session-empty {
  padding: 22px 8px;
  color: var(--el-text-color-placeholder);
  font-size: 11px;
  text-align: center;
}

.session-item {
  display: flex;
  align-items: center;
  min-height: 52px;
  margin-bottom: 5px;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 7px 8px;
  gap: 8px;
  cursor: pointer;
}

.session-item:hover,
.session-item.is-active {
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.session-item.is-archived .session-content {
  opacity: 0.65;
}

.session-icon {
  display: inline-flex;
  flex: 0 0 28px;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}

.session-item.is-active .session-icon {
  background: rgb(var(--primary-color) / 12%);
  color: rgb(var(--primary-color));
}

.session-content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.session-content b {
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-content small {
  margin-top: 3px;
  color: var(--el-text-color-placeholder);
  font-size: 10px;
}

.session-actions {
  display: none;
  align-items: center;
  gap: 1px;
}

.session-item:hover .session-actions,
.session-item.is-active .session-actions {
  display: flex;
}

.session-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.session-actions button:hover {
  background: var(--el-fill-color);
  color: rgb(var(--primary-color));
}

.rag-policy {
  display: flex;
  align-items: flex-start;
  margin-top: 10px;
  border-radius: 7px;
  background: var(--el-color-primary-light-9);
  padding: 10px;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 1.55;
}

.rag-policy > :first-child {
  flex: none;
  margin-top: 2px;
  color: rgb(var(--primary-color));
  font-size: 16px;
}

.chat-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 13px 16px;
}

.chat-heading > span {
  width: 34px;
  height: 34px;
  font-size: 17px;
}

.chat-heading h2 {
  margin: 0;
  font-size: 15px;
}

.chat-heading p {
  display: flex;
  align-items: center;
  margin: 2px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.message-list {
  position: relative;
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 20px clamp(14px, 4vw, 48px);
}

.load-more-row {
  margin-bottom: 18px;
  text-align: center;
}

.chat-empty {
  display: flex;
  height: 100%;
  min-height: 320px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.chat-empty > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: rgb(var(--primary-color) / 9%);
  color: rgb(var(--primary-color));
  font-size: 27px;
}

.chat-empty h3 {
  margin: 14px 0 4px;
  color: var(--el-text-color-primary);
  font-size: 15px;
}

.chat-empty p {
  max-width: 420px;
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
}

.message-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 22px;
  gap: 10px;
}

.message-row.is-user {
  flex-direction: row-reverse;
}

.message-avatar {
  display: inline-flex;
  flex: 0 0 32px;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgb(var(--primary-color) / 10%);
  color: rgb(var(--primary-color));
}

.is-user .message-avatar {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.message-body {
  max-width: min(720px, 82%);
}

.message-content {
  border-radius: 4px 12px 12px;
  background: var(--el-fill-color-light);
  padding: 11px 13px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.75;
  white-space: pre-wrap;
}

.message-content.is-failed {
  border: 1px solid var(--el-color-danger-light-7);
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1.05em;
  margin-left: 2px;
  background: var(--el-color-primary);
  vertical-align: -0.15em;
  animation: stream-cursor-blink 0.9s steps(1) infinite;
}

.stream-stage {
  display: flex;
  align-items: center;
  margin-top: 6px;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.stream-stage i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-primary);
  animation: pulse 1.2s infinite;
}

.citation-reference {
  display: inline;
  margin-inline: 1px;
  border: 0;
  background: transparent;
  padding: 0 2px;
  color: rgb(var(--primary-color));
  font: inherit;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  vertical-align: super;
  cursor: pointer;
}

.citation-reference:hover {
  border-radius: 3px;
  background: rgb(var(--primary-color) / 10%);
}

.citation-reference:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--el-color-primary-light-5);
  outline-offset: 1px;
}

.is-user .message-content {
  border-radius: 12px 4px 12px 12px;
  background: rgb(var(--primary-color));
  color: white;
}

.citation-list {
  display: flex;
  flex-direction: column;
  margin-top: 10px;
  gap: 7px;
}

.citation-list > strong {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.citation-card {
  display: flex;
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 7px;
  background: var(--el-bg-color);
  padding: 9px;
  gap: 9px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  scroll-margin-block: 80px;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.citation-card:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.citation-card.is-highlighted {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
}

.citation-index {
  display: inline-flex;
  flex: 0 0 20px;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 5px;
  background: rgb(var(--primary-color) / 10%);
  color: rgb(var(--primary-color));
  font-size: 10px;
  font-weight: 700;
}

.citation-card > span:last-child {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.citation-card b {
  font-size: 11px;
}

.citation-card small {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 10px;
}

.citation-card em {
  overflow: hidden;
  margin-top: 5px;
  color: var(--el-text-color-regular);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.answering-indicator {
  display: flex;
  align-items: center;
  border-radius: 4px 12px 12px;
  background: var(--el-fill-color-light);
  padding: 12px;
  gap: 5px;
}

.answering-indicator i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
  animation: pulse 1.2s infinite;
}

.answering-indicator i:nth-child(2) {
  animation-delay: 0.15s;
}

.answering-indicator i:nth-child(3) {
  animation-delay: 0.3s;
}

.answering-indicator span {
  margin-left: 5px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.chat-composer {
  flex: none;
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px clamp(14px, 4vw, 48px);
}

.composer-box {
  border: 1px solid var(--el-border-color);
  border-radius: 9px;
  padding: 7px 8px 8px;
  transition: border-color 0.2s;
}

.composer-box:focus-within {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-9);
}

.composer-box :deep(.el-textarea__inner) {
  box-shadow: none;
  padding: 5px;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.composer-actions > span {
  color: var(--el-text-color-placeholder);
  font-size: 10px;
}

@keyframes pulse {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }

  30% {
    transform: translateY(-3px);
    opacity: 1;
  }
}

@keyframes stream-cursor-blink {
  0%,
  50% {
    opacity: 1;
  }

  51%,
  100% {
    opacity: 0;
  }
}

@media (max-width: 800px) {
  .knowledge-chat-page {
    height: auto;
    min-height: 760px;
    grid-template-columns: 1fr;
  }

  .chat-side-panel {
    padding: 12px;
  }

  .scope-form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 10px;
  }

  .session-list {
    max-height: 220px;
  }

  .rag-policy {
    display: none;
  }

  .chat-main {
    min-height: 620px;
  }
  .audit-layout {
    grid-template-columns: 1fr;
  }
  .audit-session-list {
    max-height: 260px;
    overflow: auto;
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }
}

@media (max-width: 520px) {
  .scope-form {
    grid-template-columns: 1fr;
  }

  .message-body {
    max-width: 88%;
  }

  .chat-header {
    padding: 10px 12px;
  }

  .chat-header > .el-button {
    padding-inline: 8px;
  }

  .message-list {
    padding: 14px 10px;
  }

  .chat-composer {
    padding: 10px;
  }
}
</style>
