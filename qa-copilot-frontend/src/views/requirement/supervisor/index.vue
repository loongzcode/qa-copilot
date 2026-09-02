<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import dayjs from 'dayjs';
import {
  fetchCancelSupervisorRun,
  fetchCreateSupervisorRun,
  fetchCreateSupervisorSession,
  fetchDecideSupervisorStepApproval,
  fetchExecuteSupervisorRun,
  fetchGetKnowledgeBaseList,
  fetchGetProjectList,
  fetchGetProjectModules,
  fetchGetRequirementList,
  fetchGetSupervisorRunDetail,
  fetchGetSupervisorRuns,
  fetchGetSupervisorSessions
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'SupervisorRuns' });

const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 760px)');
const loading = ref(false);
const creating = ref(false);
const detailLoading = ref(false);
const cancelling = ref(false);
const executing = ref(false);
const approvingStepId = ref<number | null>(null);
const createDialogVisible = ref(false);
const detailDrawerVisible = ref(false);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const records = ref<Api.Supervisor.Run[]>([]);
const sessions = ref<Api.Supervisor.Session[]>([]);
const activeSessionId = ref<number | null>(null);
const requirements = ref<Api.RequirementManage.Requirement[]>([]);
const knowledgeBases = ref<Api.KnowledgeManage.KnowledgeBase[]>([]);
const modules = ref<Api.ProjectManage.ProjectModule[]>([]);
const activeRun = ref<Api.Supervisor.RunDetail | null>(null);
const total = ref(0);
let pollingTimer: ReturnType<typeof setInterval> | null = null;

const searchParams = reactive<Api.Supervisor.RunSearchParams>({
  current: 1,
  size: 50,
  status: undefined,
  sessionId: undefined
});
const createForm = reactive({
  goal: '',
  requirementId: undefined as number | undefined,
  knowledgeBaseId: undefined as number | undefined,
  moduleId: undefined as number | undefined
});

const canRun = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('supervisor:run');
});

const canApprove = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('supervisor:approve');
});

const cancellableStatuses: Api.Supervisor.RunStatus[] = ['PLANNING', 'READY', 'WAITING_APPROVAL'];
const hasRunningRun = computed(
  () => records.value.some(item => item.status === 'RUNNING') || activeRun.value?.status === 'RUNNING'
);
const chatRuns = computed(() => [...records.value].reverse());

const runStatusOptions: Array<{ label: string; value: Api.Supervisor.RunStatus }> = [
  { label: '规划中', value: 'PLANNING' },
  { label: '计划被拒绝', value: 'PLAN_REJECTED' },
  { label: '待执行', value: 'READY' },
  { label: '等待人工审批', value: 'WAITING_APPROVAL' },
  { label: '执行中', value: 'RUNNING' },
  { label: '已成功', value: 'SUCCEEDED' },
  { label: '失败', value: 'FAILED' },
  { label: '已取消', value: 'CANCELLED' }
];

function runStatusLabel(status: Api.Supervisor.RunStatus) {
  return runStatusOptions.find(item => item.value === status)?.label ?? status;
}

function runStatusType(status: Api.Supervisor.RunStatus) {
  const map: Record<Api.Supervisor.RunStatus, 'info' | 'primary' | 'warning' | 'success' | 'danger'> = {
    PLANNING: 'primary',
    PLAN_REJECTED: 'danger',
    READY: 'success',
    WAITING_APPROVAL: 'warning',
    RUNNING: 'primary',
    SUCCEEDED: 'success',
    FAILED: 'danger',
    CANCELLED: 'info'
  };
  return map[status];
}

function stepStatusLabel(status: Api.Supervisor.StepStatus) {
  return {
    PROPOSED: '已提出',
    REJECTED: '已拒绝',
    READY: '校验通过',
    WAITING_APPROVAL: '等待人工审批',
    RUNNING: '执行中',
    SUCCEEDED: '已成功',
    FAILED: '失败',
    SKIPPED: '已跳过',
    CANCELLED: '已取消'
  }[status];
}

function stepStatusType(status: Api.Supervisor.StepStatus) {
  if (status === 'SUCCEEDED' || status === 'READY') return 'success';
  if (status === 'FAILED' || status === 'REJECTED') return 'danger';
  if (status === 'WAITING_APPROVAL') return 'warning';
  if (status === 'RUNNING') return 'primary';
  return 'info';
}

function riskLabel(risk: Api.Supervisor.RiskLevel) {
  return { LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险' }[risk];
}

function riskType(risk: Api.Supervisor.RiskLevel) {
  return ({ LOW: 'success', MEDIUM: 'warning', HIGH: 'danger' } as const)[risk];
}

function decisionLabel(decision: Api.Supervisor.StepDecision) {
  return { READY: '允许执行', BLOCKED_APPROVAL: '需要人工审批', REJECTED: '拒绝执行' }[decision];
}

function formatTime(value: string | null) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

function hasObjectContent(value: Record<string, unknown>) {
  return Object.keys(value).length > 0;
}

async function getProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getData(silent = false) {
  if (!activeProjectId.value) return;
  if (!silent) loading.value = true;
  const { data, error } = await fetchGetSupervisorRuns(activeProjectId.value, searchParams);
  if (!silent) loading.value = false;
  if (!error) {
    records.value = data.records;
    total.value = data.total;
  }
}

async function getContextOptions() {
  if (!activeProjectId.value) return;
  const [requirementResult, knowledgeResult, moduleResult] = await Promise.all([
    fetchGetRequirementList(activeProjectId.value, { current: 1, size: 200, keyword: '' }),
    fetchGetKnowledgeBaseList(activeProjectId.value, { current: 1, size: 200, keyword: '' }),
    fetchGetProjectModules(activeProjectId.value, { keyword: '' })
  ]);
  if (!requirementResult.error) requirements.value = requirementResult.data.records;
  if (!knowledgeResult.error) knowledgeBases.value = knowledgeResult.data.records;
  if (!moduleResult.error) modules.value = moduleResult.data;
}

async function getSessions() {
  if (!activeProjectId.value) return;
  const { data, error } = await fetchGetSupervisorSessions(activeProjectId.value);
  if (error) return;
  sessions.value = data;
  if (!activeSessionId.value || !data.some(item => item.id === activeSessionId.value)) {
    activeSessionId.value = data[0]?.id ?? null;
  }
  searchParams.sessionId = activeSessionId.value ?? undefined;
}

async function createSession() {
  if (!activeProjectId.value) return;
  const { data, error } = await fetchCreateSupervisorSession(activeProjectId.value);
  if (error) return;
  await getSessions();
  activeSessionId.value = data.id;
  searchParams.sessionId = data.id;
  await getData();
}

async function selectSession(sessionId: number) {
  activeSessionId.value = sessionId;
  searchParams.sessionId = sessionId;
  searchParams.current = 1;
  await getData();
}

/** 运行期间定时读取数据库状态；终态出现后下一轮会自然停止请求。 */
function startPolling() {
  if (pollingTimer) clearInterval(pollingTimer);
  pollingTimer = setInterval(async () => {
    if (!hasRunningRun.value || !activeProjectId.value) return;
    await getData(true);
    if (detailDrawerVisible.value && activeRun.value?.status === 'RUNNING') {
      const { data, error } = await fetchGetSupervisorRunDetail(activeProjectId.value, activeRun.value.id);
      if (!error) activeRun.value = data;
    }
  }, 3000);
}

async function handleProjectChange() {
  searchParams.current = 1;
  activeRun.value = null;
  await Promise.all([getContextOptions(), getSessions()]);
  await getData();
}

async function submitCreate() {
  if (!activeProjectId.value || !createForm.goal.trim()) {
    window.$message?.warning('请先选择项目并填写目标');
    return;
  }
  const businessContext: Api.Supervisor.BusinessContext = {};
  if (createForm.requirementId) businessContext.requirementId = createForm.requirementId;
  if (createForm.knowledgeBaseId) businessContext.knowledgeBaseId = createForm.knowledgeBaseId;
  if (createForm.moduleId) businessContext.moduleId = createForm.moduleId;

  creating.value = true;
  if (!activeSessionId.value) {
    const sessionResult = await fetchCreateSupervisorSession(
      activeProjectId.value,
      createForm.goal.trim().slice(0, 60)
    );
    if (sessionResult.error) {
      creating.value = false;
      return;
    }
    activeSessionId.value = sessionResult.data.id;
    searchParams.sessionId = sessionResult.data.id;
  }
  const { data, error } = await fetchCreateSupervisorRun(activeProjectId.value, {
    goal: createForm.goal.trim(),
    businessContext,
    sessionId: activeSessionId.value
  });
  creating.value = false;
  if (error) return;
  createDialogVisible.value = false;
  createForm.goal = '';
  window.$message?.success('受控计划已生成；当前版本不会自动执行步骤');
  await Promise.all([getSessions(), getData()]);
  activeRun.value = data;
  detailDrawerVisible.value = true;
}

async function openDetail(row: Api.Supervisor.Run) {
  if (!activeProjectId.value) return;
  detailDrawerVisible.value = true;
  detailLoading.value = true;
  const { data, error } = await fetchGetSupervisorRunDetail(activeProjectId.value, row.id);
  detailLoading.value = false;
  if (error) {
    detailDrawerVisible.value = false;
    return;
  }
  activeRun.value = data;
}

async function cancelRun() {
  if (!activeProjectId.value || !activeRun.value) return;
  try {
    await window.$messageBox?.confirm('只会取消尚未执行的计划和步骤，是否继续？', '取消运行', {
      type: 'warning',
      confirmButtonText: '确认取消',
      cancelButtonText: '返回'
    });
  } catch {
    return;
  }
  cancelling.value = true;
  const { data, error } = await fetchCancelSupervisorRun(activeProjectId.value, activeRun.value.id);
  cancelling.value = false;
  if (error) return;
  activeRun.value = data;
  window.$message?.success('运行已取消');
  await getData();
}

async function executeRun() {
  if (!activeProjectId.value || !activeRun.value) return;
  try {
    await window.$messageBox?.confirm(
      '系统将按依赖顺序执行已校验步骤。当前开放能力均为只读查询，是否启动？',
      '启动 Supervisor',
      {
        type: 'info',
        confirmButtonText: '确认启动',
        cancelButtonText: '返回'
      }
    );
  } catch {
    return;
  }
  executing.value = true;
  const { data, error } = await fetchExecuteSupervisorRun(activeProjectId.value, activeRun.value.id);
  executing.value = false;
  if (error) return;
  activeRun.value = data;
  window.$message?.success('任务已可靠提交，请保持 Supervisor Worker 运行');
  await getData(true);
}

async function decideStep(step: Api.Supervisor.PlanStep, decision: 'APPROVED' | 'REJECTED') {
  if (!activeProjectId.value || !activeRun.value) return;
  const approving = decision === 'APPROVED';
  try {
    await window.$messageBox?.confirm(
      approving
        ? '批准后，如果这是最后一个待审批步骤，系统会立即提交后台执行。是否继续？'
        : '驳回会取消整条计划，其他尚未执行步骤也会取消。是否继续？',
      approving ? '批准风险步骤' : '驳回风险步骤',
      {
        type: approving ? 'warning' : 'error',
        confirmButtonText: approving ? '批准并继续' : '确认驳回',
        cancelButtonText: '返回'
      }
    );
  } catch {
    return;
  }
  approvingStepId.value = step.id;
  const { data, error } = await fetchDecideSupervisorStepApproval(
    activeProjectId.value,
    { runId: activeRun.value.id, stepId: step.id },
    {
      decision,
      comment: approving ? '页面确认批准' : '页面确认驳回'
    }
  );
  approvingStepId.value = null;
  if (error) return;
  activeRun.value = data;
  window.$message?.success(approving ? '审批已通过，满足条件后将自动执行' : '步骤已驳回，计划已取消');
  await getData(true);
}

onMounted(async () => {
  await getProjects();
  await Promise.all([getContextOptions(), getSessions()]);
  await getData();
  startPolling();
});

onBeforeUnmount(() => {
  if (pollingTimer) clearInterval(pollingTimer);
});
</script>

<template>
  <div class="supervisor-page">
    <ElCard shadow="never" class="hero-card">
      <div class="hero-row">
        <div>
          <div class="hero-title">Supervisor Agent</div>
          <div class="hero-description">
            把开放目标拆成受控步骤，并在执行前完成能力白名单、用户权限、风险和人工审批校验。
          </div>
        </div>
        <ElButton v-if="canRun" type="primary" @click="createSession">
          <template #icon><SvgIcon icon="mdi:robot-outline" /></template>
          新建会话
        </ElButton>
      </div>
    </ElCard>

    <ElCard shadow="never" class="list-card">
      <div class="filters">
        <ElSelect
          v-model="activeProjectId"
          class="project-select"
          placeholder="请选择项目"
          filterable
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElSelect
          v-model="searchParams.status"
          class="status-select"
          placeholder="全部运行状态"
          clearable
          @change="
            searchParams.current = 1;
            getData();
          "
        >
          <ElOption v-for="item in runStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect
          v-model="activeSessionId"
          class="status-select"
          placeholder="选择会话"
          filterable
          @change="selectSession"
        >
          <ElOption v-for="item in sessions" :key="item.id" :label="item.title" :value="item.id" />
        </ElSelect>
        <ElButton type="primary" plain @click="createSession">新建会话</ElButton>
        <ElButton :loading="loading" @click="getData()">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新
        </ElButton>
      </div>

      <div v-loading="loading" class="supervisor-chat-thread">
        <ElEmpty v-if="!chatRuns.length" description="发送一个质量目标，Supervisor 会在这里回复受控计划" />
        <template v-for="run in chatRuns" :key="run.id">
          <div class="chat-message chat-message-user">
            <div class="chat-bubble">{{ run.goal }}</div>
          </div>
          <div class="chat-message chat-message-assistant">
            <div class="chat-avatar"><SvgIcon icon="mdi:robot-outline" /></div>
            <div class="chat-bubble assistant-bubble">
              <div class="assistant-heading">
                <strong>受控计划 #{{ run.id }}</strong>
                <ElTag :type="runStatusType(run.status)" size="small">{{ runStatusLabel(run.status) }}</ElTag>
              </div>
              <p>
                {{
                  run.status === 'PLAN_REJECTED' || run.status === 'FAILED'
                    ? run.errorMessage || '计划未通过安全校验'
                    : '计划已经生成并保存。执行、审批和失败恢复仍由后台 Run 状态机负责。'
                }}
              </p>
              <ElButton link type="primary" @click="openDetail(run)">查看计划与审批</ElButton>
            </div>
          </div>
        </template>
      </div>

      <div v-if="canRun" class="chat-composer">
        <div class="context-select-row">
          <ElSelect v-model="createForm.requirementId" clearable filterable placeholder="关联需求（可选）">
            <ElOption
              v-for="item in requirements"
              :key="item.id"
              :label="`${item.title} · V${item.version}`"
              :value="item.id"
            />
          </ElSelect>
          <ElSelect v-model="createForm.knowledgeBaseId" clearable filterable placeholder="关联知识库（可选）">
            <ElOption v-for="item in knowledgeBases" :key="item.id" :label="item.name" :value="item.id" />
          </ElSelect>
          <ElSelect v-model="createForm.moduleId" clearable filterable placeholder="关联模块（可选）">
            <ElOption v-for="item in modules" :key="item.id" :label="item.name" :value="item.id" />
          </ElSelect>
        </div>
        <div class="composer-row">
          <ElInput
            v-model="createForm.goal"
            type="textarea"
            :rows="3"
            maxlength="2000"
            placeholder="例如：分析文章发布需求的覆盖情况，并为未覆盖需求点生成补充用例计划"
            @keydown.ctrl.enter="submitCreate"
          />
          <ElButton type="primary" :loading="creating" :disabled="!createForm.goal.trim()" @click="submitCreate">
            发送
          </ElButton>
        </div>
      </div>

      <div class="pagination-row">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          :page-sizes="[10, 20, 50]"
          @current-change="getData()"
          @size-change="
            searchParams.current = 1;
            getData();
          "
        />
      </div>
    </ElCard>

    <ElDialog v-model="createDialogVisible" title="新建受控计划" :width="isMobile ? '94%' : '680px'" destroy-on-close>
      <ElAlert
        title="当前阶段只生成并校验计划，不会自动修改业务数据或调用外部系统。"
        type="info"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <ElForm label-position="top">
        <ElFormItem label="目标" required>
          <ElInput
            v-model="createForm.goal"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            placeholder="例如：分析需求 18 的覆盖情况，并为未覆盖需求点提出补充测试用例计划"
          />
        </ElFormItem>
        <div class="context-title">可选业务上下文</div>
        <div class="context-description">填写已有对象编号可减少模型猜测；不涉及的字段保持为空。</div>
        <div class="context-grid">
          <ElFormItem label="关联需求">
            <ElSelect v-model="createForm.requirementId" clearable filterable placeholder="按需求名称选择">
              <ElOption
                v-for="item in requirements"
                :key="item.id"
                :label="`${item.title} · V${item.version}`"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="关联知识库">
            <ElSelect v-model="createForm.knowledgeBaseId" clearable filterable placeholder="按知识库名称选择">
              <ElOption v-for="item in knowledgeBases" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="关联模块">
            <ElSelect v-model="createForm.moduleId" clearable filterable placeholder="按模块名称选择">
              <ElOption
                v-for="item in modules"
                :key="item.id"
                :label="`${item.name}（${item.code}）`"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
        </div>
      </ElForm>
      <template #footer>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" :disabled="!createForm.goal.trim()" @click="submitCreate">
          生成并校验计划
        </ElButton>
      </template>
    </ElDialog>

    <ElDrawer
      v-model="detailDrawerVisible"
      :size="isMobile ? '100%' : '760px'"
      destroy-on-close
      class="supervisor-drawer"
    >
      <template #header>
        <div v-if="activeRun" class="drawer-header">
          <div>
            <div class="drawer-title">运行 #{{ activeRun.id }}</div>
            <div class="drawer-subtitle">{{ activeRun.goal }}</div>
          </div>
          <ElTag :type="runStatusType(activeRun.status)">{{ runStatusLabel(activeRun.status) }}</ElTag>
        </div>
      </template>

      <div v-loading="detailLoading">
        <template v-if="activeRun">
          <div class="summary-grid">
            <div class="summary-item">
              <span>计划版本</span>
              <strong>V{{ activeRun.planVersion }}</strong>
            </div>
            <div class="summary-item">
              <span>当前步骤</span>
              <strong>{{ activeRun.currentStepNo || '-' }}</strong>
            </div>
            <div class="summary-item">
              <span>模型编号</span>
              <strong>{{ activeRun.modelId ?? '-' }}</strong>
            </div>
            <div class="summary-item">
              <span>创建时间</span>
              <strong>{{ formatTime(activeRun.createdAt) }}</strong>
            </div>
          </div>

          <ElAlert
            v-if="activeRun.errorMessage"
            :title="activeRun.errorMessage"
            type="error"
            :closable="false"
            show-icon
          />

          <ElCollapse
            v-if="hasObjectContent(activeRun.contextSnapshot) || hasObjectContent(activeRun.resultSummary)"
            class="audit-collapse"
          >
            <ElCollapseItem
              v-if="hasObjectContent(activeRun.contextSnapshot)"
              title="查看规划上下文快照"
              name="context"
            >
              <pre>{{ JSON.stringify(activeRun.contextSnapshot, null, 2) }}</pre>
            </ElCollapseItem>
            <ElCollapseItem
              v-if="hasObjectContent(activeRun.resultSummary)"
              title="查看运行结果摘要"
              name="result-summary"
            >
              <pre>{{ JSON.stringify(activeRun.resultSummary, null, 2) }}</pre>
            </ElCollapseItem>
          </ElCollapse>

          <div class="section-heading">
            <span>计划步骤</span>
            <ElTag type="info" effect="plain">{{ activeRun.steps.length }} 步</ElTag>
          </div>
          <ElTimeline class="plan-timeline">
            <ElTimelineItem
              v-for="step in activeRun.steps"
              :key="step.id"
              :timestamp="`步骤 ${step.stepNo} · ${step.capabilityCode}`"
              placement="top"
              :type="stepStatusType(step.status)"
              :hollow="step.status === 'PROPOSED'"
            >
              <ElCard shadow="never" class="step-card">
                <div class="step-heading">
                  <strong>{{ step.purpose }}</strong>
                  <div class="step-tags">
                    <ElTag size="small" :type="stepStatusType(step.status)">{{ stepStatusLabel(step.status) }}</ElTag>
                    <ElTag size="small" :type="riskType(step.riskLevel)" effect="plain">
                      {{ riskLabel(step.riskLevel) }}
                    </ElTag>
                  </div>
                </div>
                <ElDescriptions :column="1" size="small" border class="step-descriptions">
                  <ElDescriptionsItem label="安全判定">{{ decisionLabel(step.decision) }}</ElDescriptionsItem>
                  <ElDescriptionsItem label="所需权限">
                    <code>{{ step.requiredPermission || '无' }}</code>
                  </ElDescriptionsItem>
                  <ElDescriptionsItem label="前置步骤">
                    {{ step.dependsOn.length ? step.dependsOn.join('、') : '无' }}
                  </ElDescriptionsItem>
                  <ElDescriptionsItem label="人工审批">
                    {{ step.requiresHumanApproval ? '必须审批后才能执行' : '不需要' }}
                  </ElDescriptionsItem>
                </ElDescriptions>
                <ElCollapse v-if="hasObjectContent(step.argumentsSnapshot) || hasObjectContent(step.resultSnapshot)">
                  <ElCollapseItem v-if="hasObjectContent(step.argumentsSnapshot)" title="查看参数快照" name="arguments">
                    <pre>{{ JSON.stringify(step.argumentsSnapshot, null, 2) }}</pre>
                  </ElCollapseItem>
                  <ElCollapseItem v-if="hasObjectContent(step.resultSnapshot)" title="查看结果快照" name="result">
                    <pre>{{ JSON.stringify(step.resultSnapshot, null, 2) }}</pre>
                  </ElCollapseItem>
                </ElCollapse>
                <ElAlert v-if="step.errorMessage" :title="step.errorMessage" type="error" :closable="false" />
                <div v-if="step.approvalDecision" class="approval-record">
                  审批结果：{{ step.approvalDecision === 'APPROVED' ? '已批准' : '已驳回' }} · 审批人 #{{
                    step.approvalDecidedBy ?? '-'
                  }}
                  · {{ formatTime(step.approvalDecidedAt) }}
                </div>
                <div v-if="step.status === 'WAITING_APPROVAL' && canApprove" class="approval-actions">
                  <ElButton
                    type="success"
                    size="small"
                    :loading="approvingStepId === step.id"
                    @click="decideStep(step, 'APPROVED')"
                  >
                    批准并继续
                  </ElButton>
                  <ElButton
                    type="danger"
                    plain
                    size="small"
                    :loading="approvingStepId === step.id"
                    @click="decideStep(step, 'REJECTED')"
                  >
                    驳回计划
                  </ElButton>
                </div>
              </ElCard>
            </ElTimelineItem>
          </ElTimeline>

          <div class="section-heading"><span>本次权限快照</span></div>
          <div class="permission-list">
            <ElTag v-for="permission in activeRun.permissionSnapshot" :key="permission" effect="plain">
              {{ permission }}
            </ElTag>
            <span v-if="!activeRun.permissionSnapshot.length" class="empty-text">没有记录权限码</span>
          </div>
        </template>
      </div>

      <template #footer>
        <ElButton @click="detailDrawerVisible = false">关闭</ElButton>
        <ElButton
          v-if="activeRun && canRun && activeRun.status === 'READY'"
          type="primary"
          :loading="executing"
          @click="executeRun"
        >
          启动执行
        </ElButton>
        <ElButton
          v-if="activeRun && canRun && cancellableStatuses.includes(activeRun.status)"
          type="danger"
          plain
          :loading="cancelling"
          @click="cancelRun"
        >
          取消运行
        </ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style scoped>
.supervisor-chat-thread {
  min-height: 360px;
  max-height: calc(100vh - 430px);
  overflow-y: auto;
  padding: 20px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 12px;
}

.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.chat-message-user {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: min(760px, 80%);
  padding: 12px 16px;
  line-height: 1.7;
  border-radius: 14px;
}

.chat-message-user .chat-bubble {
  color: #fff;
  background: var(--el-color-primary);
  border-bottom-right-radius: 4px;
}

.chat-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  place-items: center;
}

.assistant-bubble {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-bottom-left-radius: 4px;
}

.assistant-heading {
  display: flex;
  gap: 12px;
  align-items: center;
}

.chat-composer {
  padding-top: 16px;
}

.context-select-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.composer-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: end;
}
.supervisor-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.hero-card,
.list-card {
  border-radius: 12px;
}

.hero-row,
.filters,
.drawer-header,
.step-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.hero-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.hero-description,
.context-description,
.drawer-subtitle,
.empty-text {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.filters {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.project-select {
  width: 240px;
}

.status-select {
  width: 190px;
}

.goal-cell {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.run-id {
  flex: none;
  color: var(--el-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.goal-text {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.dialog-alert {
  margin-bottom: 18px;
}

.context-title,
.section-heading {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.audit-collapse {
  margin-top: 18px;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 10px;
}

.context-grid :deep(.el-input-number),
.context-grid :deep(.el-input) {
  width: 100%;
}

.drawer-title {
  font-size: 18px;
  font-weight: 700;
}

.drawer-subtitle {
  max-width: 560px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
}

.summary-item span {
  color: var(--el-text-color-secondary);
}

.section-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 24px 0 14px;
  font-size: 16px;
}

.plan-timeline {
  padding-left: 4px;
}

.step-card {
  border-radius: 10px;
}

.step-heading {
  align-items: flex-start;
}

.step-tags,
.permission-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.step-descriptions {
  margin-top: 14px;
}

.approval-record {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.approval-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

pre {
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  margin: 0;
  border-radius: 8px;
  background: var(--el-fill-color-darker);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .hero-row,
  .drawer-header,
  .step-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .hero-row :deep(.el-button) {
    width: 100%;
  }

  .filters {
    display: grid;
    grid-template-columns: 1fr auto;
  }

  .project-select,
  .status-select {
    width: 100%;
  }

  .project-select {
    grid-column: 1 / -1;
  }

  .context-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .run-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
  }

  .pagination-row {
    justify-content: center;
  }
}
</style>
