<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDebounceFn, useIntervalFn, useMediaQuery } from '@vueuse/core';
import dayjs from 'dayjs';
import {
  fetchApproveAutomationDefinition,
  fetchCancelAutomationExecution,
  fetchCreateAutomationDefinition,
  fetchDeleteAutomationDefinition,
  fetchGetAutomationDefinitionChanges,
  fetchGetAutomationDefinitionList,
  fetchGetAutomationExecutionList,
  fetchGetAutomationExecutionReport,
  fetchGetProjectList,
  fetchGetTestCaseList,
  fetchGetTestEnvironments,
  fetchRetireAutomationDefinition,
  fetchSubmitAutomationExecution,
  fetchUpdateAutomationDefinition
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import { getAutomationIneligibleReason, getTestCaseTypeLabel } from '@/utils/automation-test-case';

defineOptions({ name: 'AutomationDefinitions' });

const router = useRouter();
const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const submitting = ref(false);
const createDialogVisible = ref(false);
const editorVisible = ref(false);
const runDialogVisible = ref(false);
const taskDrawerVisible = ref(false);
const reportDialogVisible = ref(false);
const changeDrawerVisible = ref(false);
const changeLoading = ref(false);
const definitionChanges = ref<Api.AutomationManage.DefinitionChange[]>([]);
const changeDefinitionName = ref('');
const activeProjectId = ref<number | null>(null);
const selectedTestCaseId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const testCaseOptions = ref<Api.RequirementManage.TestCase[]>([]);
const records = ref<Api.AutomationManage.Definition[]>([]);
const total = ref(0);
const editingId = ref<number | null>(null);
const editorName = ref('');
const editorJson = ref('');
const executionLoading = ref(false);
const executionSubmitting = ref(false);
const cancellingTaskId = ref<number | null>(null);
const selectedDefinition = ref<Api.AutomationManage.Definition | null>(null);
const selectedEnvironmentId = ref<number | null>(null);
const executionTimeoutSeconds = ref(300);
const environmentOptions = ref<Api.ProjectManage.TestEnvironment[]>([]);
const executionTasks = ref<Api.AutomationManage.ExecutionTask[]>([]);
const executionReport = ref<Api.AutomationManage.ExecutionReport | null>(null);
const executionTotal = ref(0);
const reportLoading = ref(false);

const searchParams = reactive<Api.AutomationManage.DefinitionSearchParams>({
  current: 1,
  size: 10,
  keyword: '',
  status: undefined
});
const executionSearchParams = reactive<Api.AutomationManage.ExecutionSearchParams>({
  current: 1,
  size: 10,
  status: undefined
});

const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('automation:definition:manage');
});
const canApprove = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('automation:definition:approve');
});
const canRun = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('automation:run');
});
const canManageEnvironments = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:environment:manage');
});
const convertibleTestCaseCount = computed(
  () => testCaseOptions.value.filter(item => !getAutomationIneligibleReason(item)).length
);

function statusLabel(status: Api.AutomationManage.DefinitionStatus) {
  return { DRAFT: '草稿', APPROVED: '已审批', RETIRED: '已退出' }[status];
}

function statusType(status: Api.AutomationManage.DefinitionStatus) {
  return { DRAFT: 'warning', APPROVED: 'success', RETIRED: 'info' }[status] as 'warning' | 'success' | 'info';
}

function changeActionLabel(action: Api.AutomationManage.DefinitionChangeAction) {
  return { CREATED: '创建', UPDATED: '编辑', APPROVED: '审批', RETIRED: '退出', DELETED: '删除' }[action];
}

function changeActionType(action: Api.AutomationManage.DefinitionChangeAction) {
  const types = {
    CREATED: 'primary',
    UPDATED: 'warning',
    APPROVED: 'success',
    RETIRED: 'info',
    DELETED: 'danger'
  } as const;
  return types[action];
}

async function openDefinitionChanges(row: Api.AutomationManage.Definition) {
  if (!activeProjectId.value) return;
  changeDefinitionName.value = `${row.name} · V${row.version}`;
  definitionChanges.value = [];
  changeDrawerVisible.value = true;
  changeLoading.value = true;
  const { data, error } = await fetchGetAutomationDefinitionChanges(activeProjectId.value, row.id);
  changeLoading.value = false;
  if (!error) definitionChanges.value = data;
}

function executionStatusLabel(status: Api.AutomationManage.ExecutionStatus) {
  return {
    PENDING: '等待执行',
    RUNNING: '执行中',
    CANCEL_REQUESTED: '取消中',
    PASSED: '通过',
    FAILED: '失败',
    TIMED_OUT: '超时',
    CANCELLED: '已取消'
  }[status];
}

function executionStatusType(status: Api.AutomationManage.ExecutionStatus) {
  const types = {
    PENDING: 'info',
    RUNNING: 'primary',
    CANCEL_REQUESTED: 'warning',
    PASSED: 'success',
    FAILED: 'danger',
    TIMED_OUT: 'danger',
    CANCELLED: 'info'
  } as const;
  return types[status];
}

function canCancelTask(status: Api.AutomationManage.ExecutionStatus) {
  return status === 'PENDING' || status === 'RUNNING';
}

function canViewReport(status: Api.AutomationManage.ExecutionStatus) {
  return ['PASSED', 'FAILED', 'TIMED_OUT', 'CANCELLED'].includes(status);
}

function stepStatusLabel(status: Api.AutomationManage.StepStatus) {
  return { PASSED: '通过', FAILED: '失败', SKIPPED: '跳过' }[status];
}

function stepStatusType(status: Api.AutomationManage.StepStatus) {
  return { PASSED: 'success', FAILED: 'danger', SKIPPED: 'info' }[status] as 'success' | 'danger' | 'info';
}

function assertionTypeLabel(type: Api.AutomationManage.AssertionType) {
  return {
    STATUS_CODE: '状态码相等',
    JSON_PATH_EQUALS: 'JSON 路径值相等',
    JSON_PATH_EXISTS: 'JSON 路径存在',
    HEADER_EQUALS: '响应头相等',
    BODY_CONTAINS: '正文包含内容',
    RESPONSE_TIME_LE: '响应时间不超过上限'
  }[type];
}

async function getProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getData() {
  if (!activeProjectId.value) return;
  loading.value = true;
  const { data, error } = await fetchGetAutomationDefinitionList(activeProjectId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;
  if (!error) {
    records.value = data.records;
    total.value = data.total;
  }
}

async function getConvertibleTestCases() {
  if (!activeProjectId.value) return;
  const { data, error } = await fetchGetTestCaseList(activeProjectId.value, {
    current: 1,
    size: 100,
    keyword: '',
    status: 'PUBLISHED'
  });
  if (error) return;
  // 不再静默过滤不合格用例：保留所有已发布用例，并在下拉框中显示不可转换原因。
  testCaseOptions.value = data.records;
}

async function handleProjectChange() {
  searchParams.current = 1;
  selectedTestCaseId.value = null;
  testCaseOptions.value = [];
  executionTasks.value = [];
  executionSearchParams.current = 1;
  await getData();
}

const handleSearch = useDebounceFn(() => {
  searchParams.current = 1;
  void getData();
}, 300);

async function openCreateDialog() {
  selectedTestCaseId.value = null;
  await getConvertibleTestCases();
  createDialogVisible.value = true;
}

async function createDefinition() {
  if (!activeProjectId.value || !selectedTestCaseId.value) {
    window.$message?.warning('请选择一个可转换的接口用例');
    return;
  }
  submitting.value = true;
  const { error } = await fetchCreateAutomationDefinition(activeProjectId.value, selectedTestCaseId.value);
  submitting.value = false;
  if (error) return;
  createDialogVisible.value = false;
  window.$message?.success('自动化定义草稿已创建');
  await getData();
}

function openEditor(row: Api.AutomationManage.Definition) {
  editingId.value = row.id;
  editorName.value = row.name;
  editorJson.value = JSON.stringify(row.definition, null, 2);
  editorVisible.value = true;
}

async function saveDefinition() {
  if (!activeProjectId.value || !editingId.value) return;
  let definition: Api.AutomationManage.DefinitionSpec;
  try {
    definition = JSON.parse(editorJson.value) as Api.AutomationManage.DefinitionSpec;
  } catch {
    window.$message?.error('定义内容不是合法 JSON，请检查逗号和引号');
    return;
  }
  if (!editorName.value.trim()) {
    window.$message?.warning('请输入定义名称');
    return;
  }
  submitting.value = true;
  const { error } = await fetchUpdateAutomationDefinition(activeProjectId.value, editingId.value, {
    name: editorName.value.trim(),
    definition
  });
  submitting.value = false;
  if (error) return;
  editorVisible.value = false;
  window.$message?.success('自动化定义已保存并通过协议校验');
  await getData();
}

async function approveDefinition(row: Api.AutomationManage.Definition) {
  if (!activeProjectId.value) return;
  await ElMessageBox.confirm(
    `确认审批“${row.name}”V${row.version} 吗？同一用例的旧审批版本会自动退出使用。`,
    '审批自动化定义',
    { type: 'warning' }
  );
  const { error } = await fetchApproveAutomationDefinition(activeProjectId.value, row.id);
  if (error) return;
  window.$message?.success('定义已审批');
  await getData();
}

async function retireDefinition(row: Api.AutomationManage.Definition) {
  if (!activeProjectId.value) return;
  await ElMessageBox.confirm(`确认让“${row.name}”V${row.version} 退出使用吗？`, '退出自动化定义', {
    type: 'warning'
  });
  const { error } = await fetchRetireAutomationDefinition(activeProjectId.value, row.id);
  if (error) return;
  window.$message?.success('定义已退出使用');
  await getData();
}

async function deleteDefinition(row: Api.AutomationManage.Definition) {
  if (!activeProjectId.value) return;
  await ElMessageBox.confirm(`确认删除“${row.name}”V${row.version} 吗？`, '删除自动化定义', { type: 'warning' });
  const { error } = await fetchDeleteAutomationDefinition(activeProjectId.value, row.id);
  if (error) return;
  window.$message?.success('定义已删除');
  await getData();
}

async function getExecutionTasks() {
  if (!activeProjectId.value) return;
  executionLoading.value = true;
  const { data, error } = await fetchGetAutomationExecutionList(activeProjectId.value, executionSearchParams);
  executionLoading.value = false;
  if (!error) {
    executionTasks.value = data.records;
    executionTotal.value = data.total;
  }
}

async function openExecutionTasks() {
  taskDrawerVisible.value = true;
  executionSearchParams.current = 1;
  await getExecutionTasks();
}

async function openRunDialog(row: Api.AutomationManage.Definition) {
  if (!activeProjectId.value) return;
  selectedDefinition.value = row;
  selectedEnvironmentId.value = null;
  executionTimeoutSeconds.value = 300;
  const { data, error } = await fetchGetTestEnvironments(activeProjectId.value, {
    keyword: '',
    enabled: true
  });
  if (error) return;
  environmentOptions.value = data.filter(item => item.environmentType !== 'PRODUCTION');
  runDialogVisible.value = true;
}

/**
 * 功能：从自动化执行弹窗跳转到测试环境管理页面。
 * 作用：当当前项目没有可执行环境时，为用户提供明确的配置入口，并把当前项目编号带到目标页面。
 * 为什么用它：执行环境包含地址、域名白名单和加密变量，应由项目统一维护；跳转复用现有环境页面，避免在执行弹窗重复实现整套环境表单。
 */
function openEnvironmentManagement() {
  if (!activeProjectId.value) return;
  runDialogVisible.value = false;
  void router.push({
    name: 'project_environments',
    query: { projectId: String(activeProjectId.value) }
  });
}

async function submitExecution() {
  if (!activeProjectId.value || !selectedDefinition.value || !selectedEnvironmentId.value) {
    window.$message?.warning('请选择一个已启用的非生产环境');
    return;
  }
  executionSubmitting.value = true;
  const { error } = await fetchSubmitAutomationExecution(activeProjectId.value, {
    definitionId: selectedDefinition.value.id,
    environmentId: selectedEnvironmentId.value,
    timeoutSeconds: executionTimeoutSeconds.value
  });
  executionSubmitting.value = false;
  if (error) return;
  runDialogVisible.value = false;
  window.$message?.success('后台执行任务已提交');
  await openExecutionTasks();
}

async function cancelExecution(task: Api.AutomationManage.ExecutionTask) {
  if (!activeProjectId.value) return;
  cancellingTaskId.value = task.id;
  const { error } = await fetchCancelAutomationExecution(activeProjectId.value, task.id);
  cancellingTaskId.value = null;
  if (error) return;
  window.$message?.success(task.status === 'PENDING' ? '任务已取消' : '已请求终止执行进程');
  await getExecutionTasks();
}

async function openExecutionReport(task: Api.AutomationManage.ExecutionTask) {
  if (!activeProjectId.value) return;
  reportDialogVisible.value = true;
  executionReport.value = null;
  reportLoading.value = true;
  const { data, error } = await fetchGetAutomationExecutionReport(activeProjectId.value, task.id);
  reportLoading.value = false;
  if (error) {
    reportDialogVisible.value = false;
    return;
  }
  executionReport.value = data;
}

// 抽屉打开时每两秒同步一次状态；关闭抽屉后仍保留定时器，但不会发请求。
useIntervalFn(
  () => {
    if (
      taskDrawerVisible.value &&
      executionTasks.value.some(item => ['PENDING', 'RUNNING', 'CANCEL_REQUESTED'].includes(item.status))
    ) {
      void getExecutionTasks();
    }
  },
  2000,
  { immediate: false }
);

async function init() {
  await getProjects();
  await getData();
}

void init();
</script>

<template>
  <div class="automation-page">
    <ElCard class="automation-card">
      <template #header>
        <div class="automation-header">
          <div>
            <h2>自动化定义</h2>
            <p>把已发布接口用例转换为受控 JSON，经人工审批后才能交给执行器</p>
          </div>
          <div class="header-actions">
            <ElButton @click="getData">
              <SvgIcon icon="mdi:refresh" />
              刷新
            </ElButton>
            <ElButton v-if="canRun" @click="openExecutionTasks">
              <SvgIcon icon="mdi:history" />
              执行任务
            </ElButton>
            <ElButton v-if="canManage" type="primary" @click="openCreateDialog">
              <SvgIcon icon="mdi:plus" />
              从接口用例生成
            </ElButton>
          </div>
        </div>
      </template>

      <div class="automation-toolbar">
        <ElSelect v-model="activeProjectId" filterable placeholder="选择项目" @change="handleProjectChange">
          <ElOption v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElInput v-model="searchParams.keyword" clearable placeholder="搜索定义、用例编码或标题" @input="handleSearch">
          <template #prefix><SvgIcon icon="mdi:magnify" /></template>
        </ElInput>
        <ElSelect v-model="searchParams.status" clearable placeholder="全部状态" @change="getData">
          <ElOption label="草稿" value="DRAFT" />
          <ElOption label="已审批" value="APPROVED" />
          <ElOption label="已退出" value="RETIRED" />
        </ElSelect>
      </div>

      <ElAlert
        class="protocol-alert"
        type="info"
        :closable="false"
        title="这里只保存受控请求、断言和变量提取规则，不保存或执行 Python、JavaScript 等任意代码。"
      />

      <div class="automation-table-wrap">
        <ElTable v-loading="loading" height="100%" border :data="records" row-key="id">
          <ElTableColumn label="定义" min-width="300">
            <template #default="{ row }: { row: Api.AutomationManage.Definition }">
              <div class="definition-cell">
                <strong>{{ row.name }}</strong>
                <small>{{ row.testCaseTitle }} · 定义 V{{ row.version }} / 用例 V{{ row.sourceCaseVersion }}</small>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="100" align="center">
            <template #default="{ row }">
              <ElTag :type="statusType(row.status)">{{ statusLabel(row.status) }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="步骤" width="80" align="center">
            <template #default="{ row }">{{ row.definition.steps.length }}</template>
          </ElTableColumn>
          <ElTableColumn label="协议" width="80" align="center">
            <template #default="{ row }">{{ row.schemaVersion }}</template>
          </ElTableColumn>
          <ElTableColumn label="内容摘要" min-width="160">
            <template #default="{ row }">
              <code>{{ row.definitionHash.slice(0, 12) }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn label="创建人" width="120">
            <template #default="{ row }">{{ row.createdByName || '-' }}</template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" width="150">
            <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
          </ElTableColumn>
          <ElTableColumn label="操作" :width="isMobile ? 230 : 350" fixed="right" align="center">
            <template #default="{ row }: { row: Api.AutomationManage.Definition }">
              <ElButton v-if="canRun && row.status === 'APPROVED'" text type="primary" @click="openRunDialog(row)">
                执行
              </ElButton>
              <ElButton text type="primary" @click="openEditor(row)">
                {{ row.status === 'DRAFT' && canManage ? '编辑' : '查看' }}
              </ElButton>
              <ElButton text type="info" @click="openDefinitionChanges(row)">变更记录</ElButton>
              <ElButton v-if="canApprove && row.status === 'DRAFT'" text type="success" @click="approveDefinition(row)">
                审批
              </ElButton>
              <ElButton
                v-if="canApprove && row.status === 'APPROVED'"
                text
                type="warning"
                @click="retireDefinition(row)"
              >
                退出
              </ElButton>
              <ElButton v-if="canManage && row.status !== 'APPROVED'" text type="danger" @click="deleteDefinition(row)">
                删除
              </ElButton>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前项目暂无自动化定义" :image-size="72" /></template>
        </ElTable>
      </div>

      <footer class="automation-footer">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, prev, pager, next, sizes"
          @current-change="getData"
          @size-change="
            searchParams.current = 1;
            getData();
          "
        />
      </footer>
    </ElCard>

    <ElDialog v-model="createDialogVisible" title="从接口用例生成定义" :width="isMobile ? '94%' : '560px'">
      <ElAlert
        type="warning"
        :closable="false"
        title="接口自动化要求：已发布、接口测试、已标记可自动化，并且每个步骤都包含结构化 request 和 assertions。"
      />
      <ElForm label-position="top" class="dialog-form">
        <ElFormItem label="来源测试用例" required>
          <ElSelect v-model="selectedTestCaseId" filterable placeholder="请选择测试用例">
            <ElOption
              v-for="item in testCaseOptions"
              :key="item.id"
              :label="`${item.caseCode || `#${item.id}`} · ${item.title} · ${getTestCaseTypeLabel(item.caseType)}${
                getAutomationIneligibleReason(item) ? `（不可用：${getAutomationIneligibleReason(item)}）` : ''
              }`"
              :value="item.id"
              :disabled="Boolean(getAutomationIneligibleReason(item))"
            />
          </ElSelect>
        </ElFormItem>
        <ElEmpty v-if="!testCaseOptions.length" description="当前项目还没有已发布用例" :image-size="64" />
        <ElAlert
          v-else-if="!convertibleTestCaseCount"
          type="info"
          :closable="false"
          title="已有发布用例，但没有符合接口自动化条件的用例；请查看下拉选项中的具体原因。"
        />
      </ElForm>
      <template #footer>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="createDefinition">生成草稿</ElButton>
      </template>
    </ElDialog>

    <ElDrawer
      v-model="editorVisible"
      :title="editingId ? '自动化定义详情' : '自动化定义'"
      :size="isMobile ? '100%' : '760px'"
    >
      <ElForm label-position="top">
        <ElFormItem label="定义名称">
          <ElInput
            v-model="editorName"
            :disabled="records.find(item => item.id === editingId)?.status !== 'DRAFT' || !canManage"
          />
        </ElFormItem>
        <ElFormItem label="受控 JSON 定义">
          <ElInput
            v-model="editorJson"
            type="textarea"
            :rows="28"
            resize="vertical"
            class="json-editor"
            :disabled="records.find(item => item.id === editingId)?.status !== 'DRAFT' || !canManage"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="editorVisible = false">关闭</ElButton>
        <ElButton
          v-if="records.find(item => item.id === editingId)?.status === 'DRAFT' && canManage"
          type="primary"
          :loading="submitting"
          @click="saveDefinition"
        >
          保存并校验
        </ElButton>
      </template>
    </ElDrawer>

    <ElDrawer
      v-model="changeDrawerVisible"
      :title="`定义变更记录 · ${changeDefinitionName}`"
      :size="isMobile ? '100%' : '720px'"
    >
      <ElAlert
        title="这里展示创建、编辑、审批、退出和删除的不可变快照；记录与业务修改在同一个数据库事务中保存。"
        type="info"
        :closable="false"
        class="protocol-alert"
      />
      <div v-loading="changeLoading" class="change-timeline-wrap">
        <ElEmpty v-if="!changeLoading && !definitionChanges.length" description="暂无变更记录" />
        <ElTimeline v-else>
          <ElTimelineItem
            v-for="change in definitionChanges"
            :key="change.id"
            :timestamp="dayjs(change.createdAt).format('YYYY-MM-DD HH:mm:ss')"
            placement="top"
          >
            <ElCard shadow="never">
              <div class="change-title">
                <ElTag :type="changeActionType(change.action)">{{ changeActionLabel(change.action) }}</ElTag>
                <strong>定义 V{{ change.version }}</strong>
                <span>{{ change.changedByName || '系统' }}</span>
              </div>
              <ElCollapse v-if="change.beforeSnapshot || change.afterSnapshot" class="change-snapshots">
                <ElCollapseItem title="查看变更前后快照" :name="change.id">
                  <div class="snapshot-grid">
                    <div>
                      <small>变更前</small>
                      <pre>{{ JSON.stringify(change.beforeSnapshot, null, 2) || '无' }}</pre>
                    </div>
                    <div>
                      <small>变更后</small>
                      <pre>{{ JSON.stringify(change.afterSnapshot, null, 2) || '无' }}</pre>
                    </div>
                  </div>
                </ElCollapseItem>
              </ElCollapse>
            </ElCard>
          </ElTimelineItem>
        </ElTimeline>
      </div>
    </ElDrawer>

    <ElDialog v-model="runDialogVisible" title="执行自动化定义" :width="isMobile ? '94%' : '520px'">
      <ElAlert
        type="warning"
        :closable="false"
        title="执行器只允许已启用的本地、开发、测试或预发布环境，生产环境由后端强制禁止。"
      />
      <ElForm label-position="top" class="dialog-form">
        <ElFormItem label="自动化定义">
          <ElInput
            :model-value="selectedDefinition ? `${selectedDefinition.name} · V${selectedDefinition.version}` : ''"
            disabled
          />
        </ElFormItem>
        <ElFormItem label="执行环境" required>
          <ElSelect v-model="selectedEnvironmentId" filterable placeholder="请选择非生产环境">
            <ElOption
              v-for="item in environmentOptions"
              :key="item.id"
              :label="`${item.name} · ${item.baseUrl}`"
              :value="item.id"
            />
          </ElSelect>
          <div v-if="!environmentOptions.length" class="environment-empty-tip">
            <span>当前项目没有已启用的非生产环境，暂时不能执行自动化任务。</span>
            <ElButton v-if="canManageEnvironments" link type="primary" @click="openEnvironmentManagement">
              去添加测试环境
            </ElButton>
            <span v-else>请联系项目管理员添加并启用测试环境。</span>
          </div>
        </ElFormItem>
        <ElFormItem label="任务总超时（秒）">
          <ElInputNumber v-model="executionTimeoutSeconds" :min="10" :max="1800" :step="30" controls-position="right" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="runDialogVisible = false">取消</ElButton>
        <ElButton
          type="primary"
          :loading="executionSubmitting"
          :disabled="!environmentOptions.length"
          @click="submitExecution"
        >
          提交后台执行
        </ElButton>
      </template>
    </ElDialog>

    <ElDrawer v-model="taskDrawerVisible" title="自动化执行任务" :size="isMobile ? '100%' : '900px'">
      <div class="execution-toolbar">
        <ElSelect
          v-model="executionSearchParams.status"
          clearable
          placeholder="全部状态"
          @change="
            executionSearchParams.current = 1;
            getExecutionTasks();
          "
        >
          <ElOption
            v-for="statusItem in [
              'PENDING',
              'RUNNING',
              'CANCEL_REQUESTED',
              'PASSED',
              'FAILED',
              'TIMED_OUT',
              'CANCELLED'
            ]"
            :key="statusItem"
            :label="executionStatusLabel(statusItem as Api.AutomationManage.ExecutionStatus)"
            :value="statusItem"
          />
        </ElSelect>
        <ElButton :loading="executionLoading" @click="getExecutionTasks">
          <SvgIcon icon="mdi:refresh" />
          刷新
        </ElButton>
      </div>
      <ElTable v-loading="executionLoading" border :data="executionTasks" row-key="id">
        <ElTableColumn label="定义 / 环境" min-width="220">
          <template #default="{ row }: { row: Api.AutomationManage.ExecutionTask }">
            <div class="definition-cell">
              <strong>{{ row.definitionName }} · V{{ row.definitionVersion }}</strong>
              <small>{{ row.environmentName }}</small>
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="105" align="center">
          <template #default="{ row }: { row: Api.AutomationManage.ExecutionTask }">
            <ElTag :type="executionStatusType(row.status)">{{ executionStatusLabel(row.status) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="进度" width="120">
          <template #default="{ row }"><ElProgress :percentage="row.progress" :stroke-width="8" /></template>
        </ElTableColumn>
        <ElTableColumn label="结果" min-width="180" show-overflow-tooltip>
          <template #default="{ row }: { row: Api.AutomationManage.ExecutionTask }">
            {{ row.errorMessage || (row.status === 'PASSED' ? '全部断言通过' : row.currentStage) }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="提交时间" width="150">
          <template #default="{ row }">{{ dayjs(row.createdAt).format('YYYY-MM-DD HH:mm') }}</template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="140" fixed="right" align="center">
          <template #default="{ row }: { row: Api.AutomationManage.ExecutionTask }">
            <ElButton v-if="canViewReport(row.status)" text type="primary" @click="openExecutionReport(row)">
              报告
            </ElButton>
            <ElButton
              v-if="canCancelTask(row.status)"
              text
              type="danger"
              :loading="cancellingTaskId === row.id"
              @click="cancelExecution(row)"
            >
              取消
            </ElButton>
            <span v-else>-</span>
          </template>
        </ElTableColumn>
        <template #empty><ElEmpty description="暂无执行任务" :image-size="72" /></template>
      </ElTable>
      <footer class="automation-footer">
        <ElPagination
          v-model:current-page="executionSearchParams.current"
          v-model:page-size="executionSearchParams.size"
          :total="executionTotal"
          :page-sizes="[10, 20, 30]"
          layout="total, prev, pager, next, sizes"
          @current-change="getExecutionTasks"
          @size-change="
            executionSearchParams.current = 1;
            getExecutionTasks();
          "
        />
      </footer>
    </ElDrawer>

    <ElDialog v-model="reportDialogVisible" title="自动化执行报告" :width="isMobile ? '96%' : '920px'" top="5vh">
      <div v-loading="reportLoading" class="report-body">
        <template v-if="executionReport">
          <ElDescriptions :column="isMobile ? 1 : 4" border>
            <ElDescriptionsItem label="定义">
              {{ executionReport.task.definitionName }} · V{{ executionReport.task.definitionVersion }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="环境">{{ executionReport.task.environmentName }}</ElDescriptionsItem>
            <ElDescriptionsItem label="状态">
              <ElTag :type="executionStatusType(executionReport.task.status)">
                {{ executionStatusLabel(executionReport.task.status) }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="总耗时">
              {{ executionReport.task.resultSummary.durationMs ?? '-' }} ms
            </ElDescriptionsItem>
            <ElDescriptionsItem label="通过 / 失败 / 跳过" :span="isMobile ? 1 : 2">
              {{ executionReport.task.resultSummary.passedSteps ?? 0 }} /
              {{ executionReport.task.resultSummary.failedSteps ?? 0 }} /
              {{ executionReport.task.resultSummary.skippedSteps ?? 0 }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="结论" :span="isMobile ? 1 : 2">
              {{ executionReport.task.errorMessage || executionReport.task.resultSummary.message || '-' }}
            </ElDescriptionsItem>
          </ElDescriptions>

          <ElEmpty v-if="!executionReport.steps.length" description="该任务没有可用的逐步骤结果" :image-size="70" />
          <ElCollapse v-else class="report-steps">
            <ElCollapseItem v-for="step in executionReport.steps" :key="step.id" :name="step.id">
              <template #title>
                <div class="report-step-title">
                  <ElTag :type="stepStatusType(step.status)" size="small">{{ stepStatusLabel(step.status) }}</ElTag>
                  <strong>{{ step.stepNo }}. {{ step.name }}</strong>
                  <code>{{ step.method }} {{ step.path }}</code>
                  <span>{{ step.durationMs === null ? '-' : `${step.durationMs} ms` }}</span>
                </div>
              </template>
              <ElDescriptions :column="isMobile ? 1 : 2" border size="small">
                <ElDescriptionsItem label="请求摘要">
                  查询参数：{{ step.requestSummary.queryKeys.join('、') || '无' }}； 请求头：{{
                    step.requestSummary.headerNames.join('、') || '无'
                  }}； 正文：{{ step.requestSummary.bodyType }}
                  <span v-if="step.requestSummary.bodyFieldNames.length">
                    （{{ step.requestSummary.bodyFieldNames.join('、') }}）
                  </span>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="响应摘要">
                  HTTP {{ step.statusCode ?? '-' }}；{{ step.responseSummary.contentType || '未知类型' }}；
                  {{ step.responseSummary.bodySizeBytes ?? 0 }} 字节
                </ElDescriptionsItem>
              </ElDescriptions>
              <ElTable
                v-if="step.assertions.length"
                :data="step.assertions"
                border
                size="small"
                class="assertion-table"
              >
                <ElTableColumn label="断言" min-width="180">
                  <template #default="{ row }">{{ assertionTypeLabel(row.type) }}</template>
                </ElTableColumn>
                <ElTableColumn prop="expression" label="表达式" min-width="150">
                  <template #default="{ row }">
                    <code>{{ row.expression || '-' }}</code>
                  </template>
                </ElTableColumn>
                <ElTableColumn label="结果" width="90" align="center">
                  <template #default="{ row }">
                    <ElTag :type="row.passed ? 'success' : 'danger'" size="small">
                      {{ row.passed ? '通过' : '失败' }}
                    </ElTag>
                  </template>
                </ElTableColumn>
              </ElTable>
              <ElAlert
                v-if="step.errorMessage"
                :title="step.errorMessage"
                type="error"
                :closable="false"
                class="step-error"
              />
            </ElCollapseItem>
          </ElCollapse>
        </template>
      </div>
      <template #footer><ElButton @click="reportDialogVisible = false">关闭</ElButton></template>
    </ElDialog>
  </div>
</template>

<style scoped lang="scss">
.automation-page {
  height: 100%;
  min-height: 0;
  padding: 16px;
}
.automation-card {
  display: flex;
  height: 100%;
  flex-direction: column;
}
.automation-card :deep(.el-card__body) {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}
.automation-header,
.header-actions,
.automation-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.automation-header {
  justify-content: space-between;
}
.automation-header h2 {
  margin: 0;
  font-size: 18px;
}
.automation-header p {
  margin: 5px 0 0;
  color: var(--el-text-color-secondary);
}
.automation-toolbar {
  display: grid;
  grid-template-columns: 240px minmax(280px, 1fr) 180px;
  margin-bottom: 12px;
}
.protocol-alert {
  margin-bottom: 12px;
}
.automation-table-wrap {
  min-height: 0;
  flex: 1;
}
.definition-cell {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.definition-cell small {
  color: var(--el-text-color-secondary);
}
.automation-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
.dialog-form {
  margin-top: 18px;
}
.environment-empty-tip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 20px;
}
.execution-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 12px;
}
.execution-toolbar .el-select {
  width: 180px;
}
.report-body {
  min-height: 180px;
}
.report-steps {
  margin-top: 16px;
}
.report-step-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}
.report-step-title code {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.report-step-title > span:last-child {
  margin-left: auto;
  color: var(--el-text-color-secondary);
}
.assertion-table,
.step-error {
  margin-top: 12px;
}
.json-editor :deep(textarea) {
  font-family: Consolas, 'Courier New', monospace;
  line-height: 1.55;
}
.change-timeline-wrap {
  min-height: 180px;
  padding-top: 16px;
}
.change-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.change-title span:last-child {
  margin-left: auto;
  color: var(--el-text-color-secondary);
}
.change-snapshots {
  margin-top: 12px;
}
.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.snapshot-grid pre {
  max-height: 360px;
  overflow: auto;
  padding: 10px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
@media (max-width: 700px) {
  .automation-page {
    padding: 8px;
  }
  .automation-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .header-actions {
    width: 100%;
    justify-content: flex-end;
  }
  .automation-toolbar {
    grid-template-columns: 1fr;
  }
  .snapshot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
