<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import dayjs from 'dayjs';
import {
  fetchApproveToolTask,
  fetchCreateToolTask,
  fetchExecuteToolTask,
  fetchGetFileTemplates,
  fetchGetToolConnections,
  fetchGetToolTask,
  fetchGetToolTasks,
  fetchPreviewToolTask,
  fetchRollbackToolTask,
  fetchUploadToolInputFile,
  getToolArtifactUrl
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import ProjectSelector from '../components/project-selector.vue';

defineOptions({ name: 'ToolsTasks' });
const authStore = useAuthStore();
const projectId = ref<number | null>(null);
const loading = ref(false);
const actingId = ref<number | null>(null);
const records = ref<Api.ToolManage.Task[]>([]);
const total = ref(0);
const connections = ref<Api.ToolManage.Connection[]>([]);
const templates = ref<Api.ToolManage.FileTemplate[]>([]);
const createVisible = ref(false);
const detailVisible = ref(false);
const selected = ref<Api.ToolManage.Task | null>(null);
const uploadFile = ref<File | null>(null);
type UiAction = 'NAVIGATE' | 'CLICK' | 'FILL' | 'ASSERT_VISIBLE' | 'ASSERT_TEXT' | 'ASSERT_URL';
type UiStepForm = {
  name: string;
  action: UiAction;
  path: string;
  locator: string;
  fallbackLocatorsText: string;
  value: string;
  timeoutMs: number;
};
const uiSteps = ref<UiStepForm[]>([]);
const search = reactive<Api.ToolManage.TaskSearchParams>({
  current: 1,
  size: 20,
  status: undefined,
  taskType: undefined
});
const form = reactive({
  taskType: 'MYSQL_COMPARE' as Api.ToolManage.TaskType,
  title: '',
  sourceConnectionId: null as number | null,
  targetConnectionId: null as number | null,
  templateId: null as number | null,
  recordsJson: '[\n  {"orderNo": "T001", "amount": 100.50}\n]',
  dataId: '',
  group: 'DEFAULT_GROUP',
  configType: 'yaml',
  defectConnectionId: null as number | null,
  defectTitle: '',
  defectDescription: '',
  severity: 'MEDIUM',
  executionTaskId: null as number | null,
  testCaseId: null as number | null,
  uiConnectionId: null as number | null
});
const buttons = computed(() => new Set(authStore.userInfo.buttons));
const canManage = computed(() => buttons.value.has('*') || buttons.value.has('tool:manage'));
const canApprove = computed(() => buttons.value.has('*') || buttons.value.has('tool:approve'));
const canExecute = computed(() => buttons.value.has('*') || buttons.value.has('tool:execute'));
const canRollback = computed(() => buttons.value.has('*') || buttons.value.has('tool:rollback'));

const taskLabels: Record<Api.ToolManage.TaskType, string> = {
  FILE_GENERATE: '生成账务文件',
  FILE_VALIDATE: '校验账务文件',
  MYSQL_COMPARE: '比较 MySQL 结构',
  MYSQL_SYNC: '同步 MySQL 结构',
  NACOS_COMPARE: '比较 Nacos 配置',
  NACOS_SYNC: '同步 Nacos 配置',
  DEFECT_SYNC: '同步缺陷',
  UI_AUTOMATION: 'Playwright UI 自动化'
};
const statusLabels: Record<Api.ToolManage.TaskStatus, string> = {
  DRAFT: '草稿',
  PREVIEWED: '已预览',
  PENDING_APPROVAL: '待审批',
  APPROVED: '已批准',
  REJECTED: '已拒绝',
  RUNNING: '执行中',
  SUCCEEDED: '已成功',
  FAILED: '失败',
  ROLLED_BACK: '已回滚',
  CANCELLED: '已取消'
};
const statusTypes: Record<Api.ToolManage.TaskStatus, 'info' | 'primary' | 'warning' | 'success' | 'danger'> = {
  DRAFT: 'info',
  PREVIEWED: 'primary',
  PENDING_APPROVAL: 'warning',
  APPROVED: 'success',
  REJECTED: 'danger',
  RUNNING: 'primary',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  ROLLED_BACK: 'warning',
  CANCELLED: 'info'
};
const mysqlConnections = computed(() =>
  connections.value.filter(item => item.connectionType === 'MYSQL' && item.enabled)
);
const nacosConnections = computed(() =>
  connections.value.filter(item => item.connectionType === 'NACOS' && item.enabled)
);
const defectConnections = computed(() =>
  connections.value.filter(item => item.connectionType === 'DEFECT_PLATFORM' && item.enabled)
);
const businessConnections = computed(() =>
  connections.value.filter(item => item.connectionType === 'BUSINESS_API' && item.enabled)
);
const usesConnections = computed(() => form.taskType.startsWith('MYSQL_') || form.taskType.startsWith('NACOS_'));
const isFileTask = computed(() => form.taskType.startsWith('FILE_'));

async function loadOptions() {
  if (!projectId.value) return;
  const [connectionResult, templateResult] = await Promise.all([
    fetchGetToolConnections(projectId.value),
    fetchGetFileTemplates(projectId.value)
  ]);
  if (!connectionResult.error) connections.value = connectionResult.data;
  if (!templateResult.error) templates.value = templateResult.data;
}
async function loadData() {
  if (!projectId.value) return;
  loading.value = true;
  const { data, error } = await fetchGetToolTasks(projectId.value, search);
  loading.value = false;
  if (!error) {
    records.value = data.records;
    total.value = data.total;
  }
}
function openCreate() {
  Object.assign(form, {
    taskType: 'MYSQL_COMPARE',
    title: '',
    sourceConnectionId: null,
    targetConnectionId: null,
    templateId: null,
    recordsJson: '[\n  {"orderNo": "T001", "amount": 100.50}\n]',
    dataId: '',
    group: 'DEFAULT_GROUP',
    configType: 'yaml',
    defectConnectionId: null,
    defectTitle: '',
    defectDescription: '',
    severity: 'MEDIUM',
    executionTaskId: null,
    testCaseId: null,
    uiConnectionId: null
  });
  uiSteps.value = [
    {
      name: '打开页面',
      action: 'NAVIGATE',
      path: '/',
      locator: '',
      fallbackLocatorsText: '',
      value: '',
      timeoutMs: 10000
    }
  ];
  uploadFile.value = null;
  createVisible.value = true;
}
function buildInput(): Record<string, any> {
  if (form.taskType === 'FILE_GENERATE') return { template_id: form.templateId, records: JSON.parse(form.recordsJson) };
  if (form.taskType === 'FILE_VALIDATE') return { template_id: form.templateId };
  if (form.taskType === 'DEFECT_SYNC')
    return {
      connection_id: form.defectConnectionId,
      title: form.defectTitle.trim(),
      description: form.defectDescription.trim(),
      severity: form.severity,
      execution_task_id: form.executionTaskId,
      test_case_id: form.testCaseId
    };
  if (form.taskType === 'UI_AUTOMATION')
    return {
      connection_id: form.uiConnectionId,
      steps: uiSteps.value.map(step => ({
        name: step.name.trim(),
        action: step.action,
        ...(step.action === 'NAVIGATE' ? { path: step.path.trim() } : {}),
        ...(!['NAVIGATE', 'ASSERT_URL'].includes(step.action)
          ? {
              locator: step.locator.trim(),
              fallbackLocators: step.fallbackLocatorsText
                .split('\n')
                .map(value => value.trim())
                .filter(Boolean)
            }
          : {}),
        ...(['FILL', 'ASSERT_TEXT', 'ASSERT_URL'].includes(step.action) ? { value: step.value } : {}),
        timeoutMs: step.timeoutMs
      }))
    };
  const base = { source_connection_id: form.sourceConnectionId, target_connection_id: form.targetConnectionId };
  if (form.taskType.startsWith('NACOS_'))
    return {
      ...base,
      data_id: form.dataId.trim(),
      group: form.group.trim() || 'DEFAULT_GROUP',
      config_type: form.configType
    };
  return base;
}
function toolCode(type: Api.ToolManage.TaskType) {
  return type.toLowerCase().replace('_', '.');
}
function addUiStep() {
  uiSteps.value.push({
    name: '',
    action: 'CLICK',
    path: '',
    locator: '',
    fallbackLocatorsText: '',
    value: '',
    timeoutMs: 10000
  });
}
function removeUiStep(index: number) {
  if (uiSteps.value.length > 1) uiSteps.value.splice(index, 1);
}
async function createTask() {
  if (!projectId.value || !form.title.trim()) return window.$message?.warning('请填写任务标题');
  let inputData: Record<string, any>;
  try {
    inputData = buildInput();
  } catch {
    return window.$message?.error('生成记录不是有效 JSON');
  }
  actingId.value = 0;
  const result = await fetchCreateToolTask(projectId.value, {
    toolCode: toolCode(form.taskType),
    taskType: form.taskType,
    title: form.title.trim(),
    inputData
  });
  if (!result.error && form.taskType === 'FILE_VALIDATE' && uploadFile.value)
    await fetchUploadToolInputFile(projectId.value, result.data.id, uploadFile.value);
  actingId.value = null;
  if (result.error) return;
  createVisible.value = false;
  window.$message?.success('任务草稿已创建，请先生成预览');
  await loadData();
}
async function detail(row: Api.ToolManage.Task) {
  if (!projectId.value) return;
  const { data, error } = await fetchGetToolTask(projectId.value, row.id);
  if (!error) {
    selected.value = data;
    detailVisible.value = true;
  }
}
async function act(row: Api.ToolManage.Task, action: 'preview' | 'execute' | 'rollback') {
  if (!projectId.value) return;
  actingId.value = row.id;
  const result =
    action === 'preview'
      ? await fetchPreviewToolTask(projectId.value, row.id)
      : action === 'execute'
        ? await fetchExecuteToolTask(projectId.value, row.id)
        : await fetchRollbackToolTask(projectId.value, row.id);
  actingId.value = null;
  if (result.error) return;
  window.$message?.success(
    action === 'preview' ? '可信预览已生成' : action === 'execute' ? '任务执行完成' : '任务已回滚'
  );
  await loadData();
  if (detailVisible.value) await detail(result.data);
}
async function approve(decision: 'APPROVED' | 'REJECTED') {
  if (!projectId.value || !selected.value) return;
  const { data, error } = await fetchApproveToolTask(projectId.value, selected.value.id, {
    decision,
    comment: decision === 'APPROVED' ? '已核对预览并同意执行' : '预览不符合预期'
  });
  if (!error) {
    selected.value = data;
    window.$message?.success('审批结果已保存');
    await loadData();
  }
}
function download(artifact: Api.ToolManage.Artifact) {
  if (!projectId.value || !selected.value) return;
  window.open(getToolArtifactUrl(projectId.value, selected.value.id, artifact.id), '_blank', 'noopener');
}
watch(projectId, async () => {
  search.current = 1;
  await Promise.all([loadOptions(), loadData()]);
});
onMounted(() => Promise.all([loadOptions(), loadData()]));
</script>

<template>
  <div class="tool-page">
    <ElCard class="tool-card">
      <template #header>
        <div class="tool-heading">
          <div>
            <h2>工具任务与审批</h2>
            <p>高风险操作必须绑定服务器预览哈希，审批后外部状态变化会自动使审批失效</p>
          </div>
          <div class="tool-actions">
            <ProjectSelector v-model="projectId" />
            <ElButton v-if="canManage" type="primary" @click="openCreate">
              <SvgIcon icon="mdi:plus" />
              新建任务
            </ElButton>
          </div>
        </div>
      </template>
      <div class="tool-toolbar">
        <div class="tool-actions">
          <ElSelect
            v-model="search.taskType"
            clearable
            placeholder="全部任务类型"
            style="width: 190px"
            @change="loadData"
          >
            <ElOption v-for="(label, value) in taskLabels" :key="value" :label="label" :value="value" />
          </ElSelect>
          <ElSelect v-model="search.status" clearable placeholder="全部状态" style="width: 150px" @change="loadData">
            <ElOption v-for="(label, value) in statusLabels" :key="value" :label="label" :value="value" />
          </ElSelect>
        </div>
        <ElButton @click="loadData">
          <SvgIcon icon="mdi:refresh" />
          刷新
        </ElButton>
      </div>
      <ElTable v-loading="loading" border :data="records" row-key="id">
        <ElTableColumn label="任务" min-width="260">
          <template #default="{ row }">
            <strong>{{ row.title }}</strong>
            <div class="task-sub">
              #{{ row.id }} · {{ taskLabels[row.taskType as Api.ToolManage.TaskType] }} · {{ row.toolName }}
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="风险" width="90" align="center">
          <template #default="{ row }">
            <ElTag :type="row.riskLevel === 'HIGH' ? 'danger' : row.riskLevel === 'MEDIUM' ? 'warning' : 'success'">
              {{ row.riskLevel }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="110" align="center">
          <template #default="{ row }">
            <ElTag :type="statusTypes[row.status as Api.ToolManage.TaskStatus]">
              {{ statusLabels[row.status as Api.ToolManage.TaskStatus] }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="更新时间" width="160">
          <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="210" fixed="right" align="right">
          <template #default="{ row }">
            <ElButton text @click="detail(row)">详情</ElButton>
            <ElButton
              v-if="['DRAFT', 'PREVIEWED', 'PENDING_APPROVAL', 'APPROVED'].includes(row.status)"
              text
              type="primary"
              :loading="actingId === row.id"
              @click="act(row, 'preview')"
            >
              预览
            </ElButton>
            <ElButton
              v-if="canExecute && ['PREVIEWED', 'APPROVED'].includes(row.status)"
              text
              type="success"
              :loading="actingId === row.id"
              @click="act(row, 'execute')"
            >
              执行
            </ElButton>
            <ElButton
              v-if="canRollback && row.status === 'SUCCEEDED' && row.rollbackData"
              text
              type="warning"
              :loading="actingId === row.id"
              @click="act(row, 'rollback')"
            >
              回滚
            </ElButton>
          </template>
        </ElTableColumn>
        <template #empty><ElEmpty description="暂无工具任务" /></template>
      </ElTable>
      <ElPagination
        v-model:current-page="search.current"
        v-model:page-size="search.size"
        class="task-pagination"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
      />
    </ElCard>

    <ElDrawer v-model="createVisible" :size="620" title="新建工具任务">
      <ElForm label-position="top">
        <ElFormItem label="任务类型" required>
          <ElSelect v-model="form.taskType" class="w-full">
            <ElOption v-for="(label, value) in taskLabels" :key="value" :label="label" :value="value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="任务标题" required><ElInput v-model="form.title" maxlength="200" /></ElFormItem>
        <template v-if="usesConnections">
          <div class="task-form-grid">
            <ElFormItem label="来源连接" required>
              <ElSelect v-model="form.sourceConnectionId" class="w-full">
                <ElOption
                  v-for="item in form.taskType.startsWith('MYSQL_') ? mysqlConnections : nacosConnections"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="目标连接" required>
              <ElSelect v-model="form.targetConnectionId" class="w-full">
                <ElOption
                  v-for="item in form.taskType.startsWith('MYSQL_') ? mysqlConnections : nacosConnections"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </ElSelect>
            </ElFormItem>
          </div>
        </template>
        <template v-if="isFileTask">
          <ElFormItem label="文件模板" required>
            <ElSelect v-model="form.templateId" class="w-full">
              <ElOption
                v-for="item in templates.filter(row => row.enabled)"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
          <ElFormItem v-if="form.taskType === 'FILE_GENERATE'" label="生成数据（JSON 数组）">
            <ElInput v-model="form.recordsJson" type="textarea" :rows="10" class="tool-code" />
          </ElFormItem>
          <ElFormItem v-else label="待校验文件" required>
            <input type="file" @change="uploadFile = ($event.target as HTMLInputElement).files?.[0] || null" />
          </ElFormItem>
        </template>
        <template v-if="form.taskType.startsWith('NACOS_')">
          <ElFormItem label="Data ID" required><ElInput v-model="form.dataId" /></ElFormItem>
          <div class="task-form-grid">
            <ElFormItem label="Group"><ElInput v-model="form.group" /></ElFormItem>
            <ElFormItem label="配置格式">
              <ElSelect v-model="form.configType" class="w-full">
                <ElOption label="YAML" value="yaml" />
                <ElOption label="JSON" value="json" />
                <ElOption label="Properties" value="properties" />
              </ElSelect>
            </ElFormItem>
          </div>
        </template>
        <template v-if="form.taskType === 'DEFECT_SYNC'">
          <ElFormItem label="缺陷平台连接" required>
            <ElSelect v-model="form.defectConnectionId" class="w-full">
              <ElOption v-for="item in defectConnections" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="缺陷标题" required><ElInput v-model="form.defectTitle" maxlength="300" /></ElFormItem>
          <ElFormItem label="缺陷描述" required>
            <ElInput v-model="form.defectDescription" type="textarea" :rows="7" maxlength="20000" show-word-limit />
          </ElFormItem>
          <div class="task-form-grid">
            <ElFormItem label="严重级别">
              <ElSelect v-model="form.severity" class="w-full">
                <ElOption label="低" value="LOW" />
                <ElOption label="中" value="MEDIUM" />
                <ElOption label="高" value="HIGH" />
                <ElOption label="严重" value="CRITICAL" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="自动化执行任务 ID（可选）">
              <ElInputNumber v-model="form.executionTaskId" :min="1" class="w-full" />
            </ElFormItem>
          </div>
          <ElFormItem label="测试用例 ID（可选）">
            <ElInputNumber v-model="form.testCaseId" :min="1" class="w-full" />
          </ElFormItem>
        </template>
        <template v-if="form.taskType === 'UI_AUTOMATION'">
          <ElFormItem label="被测业务连接" required>
            <ElSelect v-model="form.uiConnectionId" class="w-full">
              <ElOption v-for="item in businessConnections" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
          </ElFormItem>
          <div class="ui-step-heading">
            <strong>浏览器步骤</strong>
            <ElButton text type="primary" @click="addUiStep">
              <SvgIcon icon="mdi:plus" />
              添加步骤
            </ElButton>
          </div>
          <div v-for="(step, index) in uiSteps" :key="index" class="ui-step-card">
            <div class="ui-step-index">
              <span>{{ index + 1 }}</span>
              <ElButton text circle type="danger" :disabled="uiSteps.length === 1" @click="removeUiStep(index)">
                <SvgIcon icon="mdi:delete-outline" />
              </ElButton>
            </div>
            <div class="task-form-grid">
              <ElFormItem label="步骤名称" required><ElInput v-model="step.name" /></ElFormItem>
              <ElFormItem label="动作">
                <ElSelect v-model="step.action" class="w-full">
                  <ElOption label="打开页面" value="NAVIGATE" />
                  <ElOption label="点击" value="CLICK" />
                  <ElOption label="输入" value="FILL" />
                  <ElOption label="检查元素可见" value="ASSERT_VISIBLE" />
                  <ElOption label="检查文本" value="ASSERT_TEXT" />
                  <ElOption label="检查地址" value="ASSERT_URL" />
                </ElSelect>
              </ElFormItem>
            </div>
            <ElFormItem v-if="step.action === 'NAVIGATE'" label="站内路径" required>
              <ElInput v-model="step.path" placeholder="/login" />
            </ElFormItem>
            <template v-else-if="step.action !== 'ASSERT_URL'">
              <ElFormItem label="主定位器" required>
                <ElInput v-model="step.locator" placeholder="#submit 或 button:has-text('登录')" />
              </ElFormItem>
              <ElFormItem label="备用定位器（每行一个，可选）">
                <ElInput v-model="step.fallbackLocatorsText" type="textarea" :rows="2" />
              </ElFormItem>
            </template>
            <ElFormItem
              v-if="['FILL', 'ASSERT_TEXT', 'ASSERT_URL'].includes(step.action)"
              :label="step.action === 'FILL' ? '输入值' : '期望内容'"
              required
            >
              <ElInput v-model="step.value" />
            </ElFormItem>
          </div>
          <ElAlert type="info" :closable="false" title="受控自愈说明">
            主定位器失败时会依次尝试备用定位器；成功后只生成待审核建议，不会自动修改正式定义。
          </ElAlert>
        </template>
      </ElForm>
      <template #footer>
        <ElButton @click="createVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="actingId === 0" @click="createTask">创建草稿</ElButton>
      </template>
    </ElDrawer>

    <ElDrawer v-model="detailVisible" size="65%" title="任务详情">
      <template v-if="selected">
        <ElDescriptions border :column="2">
          <ElDescriptionsItem label="任务">{{ selected.title }}</ElDescriptionsItem>
          <ElDescriptionsItem label="状态">{{ statusLabels[selected.status] }}</ElDescriptionsItem>
          <ElDescriptionsItem label="类型">{{ taskLabels[selected.taskType] }}</ElDescriptionsItem>
          <ElDescriptionsItem label="风险">{{ selected.riskLevel }}</ElDescriptionsItem>
        </ElDescriptions>
        <h3>可信预览</h3>
        <pre class="tool-json">{{ JSON.stringify(selected.previewData, null, 2) }}</pre>
        <ElAlert v-if="selected.errorMessage" type="error" :title="selected.errorMessage" :closable="false" />
        <div v-if="canApprove && selected.status === 'PENDING_APPROVAL'" class="approval-actions">
          <ElButton type="danger" plain @click="approve('REJECTED')">拒绝</ElButton>
          <ElButton type="success" @click="approve('APPROVED')">批准执行</ElButton>
        </div>
        <h3>执行产物</h3>
        <ElEmpty v-if="!selected.artifacts.length" description="暂无产物" :image-size="60" />
        <div v-else class="artifact-list">
          <button v-for="item in selected.artifacts" :key="item.id" type="button" @click="download(item)">
            <SvgIcon icon="mdi:download-outline" />
            <span>{{ item.name }}</span>
            <small>{{ (item.sizeBytes / 1024).toFixed(1) }} KB</small>
          </button>
        </div>
        <h3>阶段日志</h3>
        <ElTimeline>
          <ElTimelineItem
            v-for="item in selected.logs"
            :key="item.id"
            :timestamp="dayjs(item.createdAt).format('YYYY-MM-DD HH:mm:ss')"
            :type="item.level === 'ERROR' ? 'danger' : 'primary'"
          >
            <strong>{{ item.stage }}</strong>
            · {{ item.message }}
          </ElTimelineItem>
        </ElTimeline>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" scoped lang="scss"></style>

<style scoped lang="scss">
.task-sub {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.task-pagination {
  justify-content: flex-end;
  margin-top: 16px;
}
.task-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.approval-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin: 14px 0;
}
.artifact-list {
  display: grid;
  gap: 8px;
}
.artifact-list button {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: transparent;
  padding: 10px;
  text-align: left;
  cursor: pointer;
}
.artifact-list small {
  color: var(--el-text-color-secondary);
}
.ui-step-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 4px 0 10px;
}
.ui-step-card {
  position: relative;
  margin-bottom: 12px;
  padding: 16px 16px 4px 52px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-extra-light);
}
.ui-step-index {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.ui-step-index > span {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
h3 {
  margin: 20px 0 10px;
  font-size: 14px;
}
@media (max-width: 700px) {
  .task-form-grid {
    grid-template-columns: 1fr;
  }
  .ui-step-card {
    padding-left: 16px;
    padding-top: 52px;
  }
  .ui-step-index {
    flex-direction: row;
  }
}
</style>
