<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCreateDataSource,
  fetchDataQueryHistory,
  fetchDataSources,
  fetchDeleteDataSource,
  fetchExecuteDataQuery,
  fetchGetProjectList,
  fetchGetTestEnvironments,
  fetchRefreshDataSourceMetadata,
  fetchTestDataSource,
  fetchUpdateDataSource
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'ProjectDataQuery' });

const route = useRoute();
const authStore = useAuthStore();
const loading = ref(false);
const executing = ref(false);
const sourceLoading = ref(false);
const sourceDrawerVisible = ref(false);
const historyDrawerVisible = ref(false);
const savingSource = ref(false);
const testingSourceId = ref<number | null>(null);
const refreshingSourceId = ref<number | null>(null);
const editingSourceId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const activeEnvironmentId = ref<number | null>(null);
const activeSourceId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const environments = ref<Api.ProjectManage.TestEnvironment[]>([]);
const sources = ref<Api.DataQuery.EnvironmentDataSource[]>([]);
const history = ref<Api.DataQuery.Execution[]>([]);
const historyTotal = ref(0);
const historyCurrent = ref(1);
const question = ref('');
const result = ref<Api.DataQuery.Execution | null>(null);
const sourceFormRef = ref<FormInstance>();

const sourceForm = reactive({
  environmentId: null as number | null,
  name: '',
  databaseType: 'MYSQL' as Api.DataQuery.DatabaseType,
  host: '',
  port: 3306,
  databaseName: '',
  schemaName: '',
  username: '',
  password: '',
  sslEnabled: false,
  charset: 'utf8mb4',
  allowedTablesText: '',
  sensitiveColumnsText: '',
  enabled: true
});

const sourceRules: FormRules = {
  environmentId: [{ required: true, message: '请选择测试环境', trigger: 'change' }],
  name: [{ required: true, message: '请输入数据源名称', trigger: 'blur' }],
  host: [{ required: true, message: '请输入数据库主机', trigger: 'blur' }],
  databaseName: [{ required: true, message: '请输入数据库名称', trigger: 'blur' }],
  username: []
};

const canManage = computed(() => hasPermission('data:query:source:manage'));
const canExecute = computed(() => hasPermission('data:query:execute'));
const activeSource = computed(() => sources.value.find(item => item.id === activeSourceId.value));
const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const environmentOptions = computed(() =>
  environments.value
    .filter(item => item.enabled && item.environmentType !== 'PRODUCTION')
    .map(item => ({ label: item.name, value: item.id }))
);
const statusMap: Record<
  Api.DataQuery.ExecutionStatus,
  { label: string; type: 'success' | 'warning' | 'danger' | 'info' }
> = {
  GENERATING: { label: '生成中', type: 'info' },
  VALIDATING: { label: '校验中', type: 'info' },
  EXECUTING: { label: '执行中', type: 'warning' },
  SUCCEEDED: { label: '成功', type: 'success' },
  REJECTED: { label: '已拦截', type: 'warning' },
  FAILED: { label: '失败', type: 'danger' }
};

function hasPermission(code: string) {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes(code);
}

function renderCell(value: unknown) {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function parseLineList(value: string) {
  return [
    ...new Set(
      value
        .split(/[\n,]/)
        .map(item => item.trim())
        .filter(Boolean)
    )
  ];
}

function parseSensitiveColumns(value: string) {
  const resultValue: Record<string, string[]> = {};
  for (const line of value
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)) {
    const [table, columns = ''] = line.split(':', 2);
    if (table?.trim()) {
      resultValue[table.trim()] = parseLineList(columns);
    }
  }
  return resultValue;
}

function formatSensitiveColumns(value: Record<string, string[]>) {
  return Object.entries(value)
    .map(([table, columns]) => `${table}:${columns.join(',')}`)
    .join('\n');
}

async function loadProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  const routeProjectId = Number(route.query.projectId) || null;
  activeProjectId.value =
    routeProjectId && projects.value.some(item => item.id === routeProjectId)
      ? routeProjectId
      : (projects.value[0]?.id ?? null);
}

async function loadEnvironments() {
  environments.value = [];
  activeEnvironmentId.value = null;
  if (!activeProjectId.value) return;
  const { data, error } = await fetchGetTestEnvironments(activeProjectId.value, { keyword: '', enabled: true });
  if (error) return;
  environments.value = data;
  activeEnvironmentId.value = environmentOptions.value[0]?.value ?? null;
}

async function loadSources() {
  sources.value = [];
  activeSourceId.value = null;
  result.value = null;
  if (!activeProjectId.value || !activeEnvironmentId.value) return;
  sourceLoading.value = true;
  const { data, error } = await fetchDataSources(activeProjectId.value, activeEnvironmentId.value);
  sourceLoading.value = false;
  if (error) return;
  sources.value = data;
  activeSourceId.value = data.find(item => item.enabled)?.id ?? data[0]?.id ?? null;
}

async function handleProjectChange() {
  await loadEnvironments();
  await loadSources();
}

async function handleEnvironmentChange() {
  await loadSources();
}

function applyDatabaseDefaults(type: Api.DataQuery.DatabaseType) {
  sourceForm.port = type === 'MYSQL' ? 3306 : 5432;
  sourceForm.schemaName = type === 'POSTGRESQL' ? 'public' : '';
  sourceForm.charset = type === 'MYSQL' ? 'utf8mb4' : 'UTF8';
}

async function openSourceDrawer(source?: Api.DataQuery.EnvironmentDataSource) {
  if (!activeProjectId.value || !activeEnvironmentId.value) {
    window.$message?.warning('请先选择项目和测试环境');
    return;
  }
  editingSourceId.value = source?.id ?? null;
  Object.assign(
    sourceForm,
    source
      ? {
          environmentId: source.environmentId,
          name: source.name,
          databaseType: source.databaseType,
          host: source.host,
          port: source.port,
          databaseName: source.databaseName,
          schemaName: source.schemaName || '',
          username: '',
          password: '',
          sslEnabled: source.sslEnabled,
          charset: source.charset,
          allowedTablesText: source.allowedTables.join('\n'),
          sensitiveColumnsText: formatSensitiveColumns(source.sensitiveColumns),
          enabled: source.enabled
        }
      : {
          environmentId: activeEnvironmentId.value,
          name: '',
          databaseType: 'MYSQL',
          host: '',
          port: 3306,
          databaseName: '',
          schemaName: '',
          username: '',
          password: '',
          sslEnabled: false,
          charset: 'utf8mb4',
          allowedTablesText: '',
          sensitiveColumnsText: '',
          enabled: true
        }
  );
  sourceDrawerVisible.value = true;
  await nextTick();
  sourceFormRef.value?.clearValidate();
}

async function submitSource() {
  if (!activeProjectId.value || !sourceForm.environmentId) return;
  const valid = await sourceFormRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (!editingSourceId.value && (!sourceForm.username.trim() || !sourceForm.password)) {
    window.$message?.warning('新建数据源必须填写只读用户名和密码');
    return;
  }
  savingSource.value = true;
  const shared = {
    name: sourceForm.name.trim(),
    host: sourceForm.host.trim(),
    port: sourceForm.port,
    databaseName: sourceForm.databaseName.trim(),
    schemaName: sourceForm.databaseType === 'POSTGRESQL' ? sourceForm.schemaName.trim() || 'public' : null,
    sslEnabled: sourceForm.sslEnabled,
    charset: sourceForm.charset.trim(),
    allowedTables: parseLineList(sourceForm.allowedTablesText),
    sensitiveColumns: parseSensitiveColumns(sourceForm.sensitiveColumnsText),
    enabled: sourceForm.enabled
  };
  const response = editingSourceId.value
    ? await fetchUpdateDataSource(activeProjectId.value, editingSourceId.value, {
        ...shared,
        ...(sourceForm.username.trim() ? { username: sourceForm.username.trim() } : {}),
        ...(sourceForm.password ? { password: sourceForm.password } : {})
      })
    : await fetchCreateDataSource(activeProjectId.value, {
        ...shared,
        environmentId: sourceForm.environmentId,
        databaseType: sourceForm.databaseType,
        username: sourceForm.username.trim(),
        password: sourceForm.password
      });
  savingSource.value = false;
  if (response.error) return;
  sourceDrawerVisible.value = false;
  await loadSources();
  activeSourceId.value = response.data.id;
  window.$message?.success(editingSourceId.value ? '数据源已更新' : '数据源已创建，请测试连接并刷新结构');
}

async function testSource(source: Api.DataQuery.EnvironmentDataSource) {
  if (!activeProjectId.value) return;
  testingSourceId.value = source.id;
  const { data, error } = await fetchTestDataSource(activeProjectId.value, source.id);
  testingSourceId.value = null;
  if (!error) window.$message?.success(`${data.message}（${data.latencyMs} ms）`);
}

async function refreshMetadata(source: Api.DataQuery.EnvironmentDataSource) {
  if (!activeProjectId.value) return;
  refreshingSourceId.value = source.id;
  const { data, error } = await fetchRefreshDataSourceMetadata(activeProjectId.value, source.id);
  refreshingSourceId.value = null;
  if (error) return;
  await loadSources();
  activeSourceId.value = source.id;
  window.$message?.success(`结构刷新完成，共读取 ${data.tableCount} 张表`);
}

async function deleteSource(source: Api.DataQuery.EnvironmentDataSource) {
  if (!activeProjectId.value) return;
  const { error } = await fetchDeleteDataSource(activeProjectId.value, source.id);
  if (!error) {
    window.$message?.success('数据源已删除');
    await loadSources();
  }
}

async function executeQuery() {
  if (!activeProjectId.value || !activeEnvironmentId.value || !activeSourceId.value) {
    window.$message?.warning('请先选择测试环境和数据源');
    return;
  }
  const value = question.value.trim();
  if (value.length < 2) {
    window.$message?.warning('请输入需要查询的数据问题');
    return;
  }
  executing.value = true;
  result.value = null;
  const { data, error } = await fetchExecuteDataQuery(activeProjectId.value, {
    environmentId: activeEnvironmentId.value,
    dataSourceId: activeSourceId.value,
    question: value
  });
  executing.value = false;
  if (!error) result.value = data;
}

async function copySql() {
  if (!result.value?.generatedSql) return;
  await navigator.clipboard.writeText(result.value.generatedSql);
  window.$message?.success('SQL 已复制');
}

async function openHistory() {
  historyDrawerVisible.value = true;
  historyCurrent.value = 1;
  await loadHistory();
}

async function loadHistory() {
  if (!activeProjectId.value) return;
  loading.value = true;
  const { data, error } = await fetchDataQueryHistory(activeProjectId.value, {
    environmentId: activeEnvironmentId.value || undefined,
    dataSourceId: activeSourceId.value || undefined,
    current: historyCurrent.value,
    size: 20
  });
  loading.value = false;
  if (!error) {
    history.value = data.records;
    historyTotal.value = data.total;
  }
}

function selectHistory(item: Api.DataQuery.Execution) {
  result.value = item;
  question.value = item.question;
  historyDrawerVisible.value = false;
}

onMounted(async () => {
  await loadProjects();
  await loadEnvironments();
  await loadSources();
});
</script>

<template>
  <div class="data-query-page">
    <ElCard shadow="never" class="query-card">
      <template #header>
        <div class="page-header">
          <div>
            <h3>智能数据查询</h3>
            <p>用自然语言查询测试环境数据，系统只会执行经过安全校验的只读 SQL。</p>
          </div>
          <div class="header-actions">
            <ElButton @click="openHistory">
              <SvgIcon icon="mdi:history" />
              查询历史
            </ElButton>
            <ElButton v-if="canManage" type="primary" plain @click="openSourceDrawer()">
              <SvgIcon icon="mdi:database-plus-outline" />
              配置数据源
            </ElButton>
          </div>
        </div>
      </template>

      <div class="selector-grid">
        <ElSelect v-model="activeProjectId" filterable placeholder="选择项目" @change="handleProjectChange">
          <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect v-model="activeEnvironmentId" placeholder="选择测试环境" @change="handleEnvironmentChange">
          <ElOption v-for="item in environmentOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect v-model="activeSourceId" :loading="sourceLoading" placeholder="选择只读数据源">
          <ElOption
            v-for="item in sources"
            :key="item.id"
            :label="item.name"
            :value="item.id"
            :disabled="!item.enabled"
          >
            <span>{{ item.name }}</span>
            <span class="option-hint">{{ item.databaseType }} · {{ item.metadataTableCount }} 表</span>
          </ElOption>
        </ElSelect>
      </div>

      <div v-if="activeSource" class="source-strip">
        <div>
          <SvgIcon icon="mdi:database-outline" />
          <strong>{{ activeSource.name }}</strong>
          <code>{{ activeSource.host }}:{{ activeSource.port }}/{{ activeSource.databaseName }}</code>
          <ElTag size="small" effect="plain">{{ activeSource.databaseType }}</ElTag>
          <ElTag v-if="activeSource.metadataCapturedAt" size="small" type="success" effect="plain">
            已读取 {{ activeSource.metadataTableCount }} 张表
          </ElTag>
          <ElTag v-else size="small" type="warning" effect="plain">尚未读取结构</ElTag>
        </div>
        <div v-if="canManage" class="source-actions">
          <ElButton text :loading="testingSourceId === activeSource.id" @click="testSource(activeSource)">
            测试连接
          </ElButton>
          <ElButton text :loading="refreshingSourceId === activeSource.id" @click="refreshMetadata(activeSource)">
            刷新结构
          </ElButton>
          <ElButton text @click="openSourceDrawer(activeSource)">编辑</ElButton>
          <ElPopconfirm title="确认删除该数据源？已有审计记录时系统会拒绝删除。" @confirm="deleteSource(activeSource)">
            <template #reference><ElButton text type="danger">删除</ElButton></template>
          </ElPopconfirm>
        </div>
      </div>

      <div class="question-panel">
        <ElInput
          v-model="question"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="例如：统计最近 7 天每天新增用户数，并按日期升序排列"
          @keydown.ctrl.enter.prevent="executeQuery"
        />
        <div class="question-footer">
          <span>Ctrl + Enter 查询。系统会限制表、字段、扫描量、结果行数和执行时间。</span>
          <ElButton
            type="primary"
            :loading="executing"
            :disabled="!canExecute || !activeSourceId"
            @click="executeQuery"
          >
            <SvgIcon icon="mdi:sparkles" />
            生成并查询
          </ElButton>
        </div>
      </div>
    </ElCard>

    <ElCard v-if="executing" shadow="never" class="result-card">
      <ElSkeleton :rows="5" animated />
      <div class="executing-tip">正在读取结构、生成 SQL、安全校验并执行只读查询……</div>
    </ElCard>

    <ElCard v-else-if="result" shadow="never" class="result-card">
      <template #header>
        <div class="result-header">
          <div>
            <ElTag :type="statusMap[result.status].type" effect="plain">{{ statusMap[result.status].label }}</ElTag>
            <strong>{{ result.question }}</strong>
          </div>
          <span>{{ result.resultRowCount }} 行 · {{ result.latencyMs }} ms</span>
        </div>
      </template>

      <ElAlert
        v-if="result.truncated"
        type="warning"
        show-icon
        :closable="false"
        title="结果已按平台上限截断，仅展示安全范围内的数据。"
      />
      <ElAlert v-if="result.errorMessage" type="error" show-icon :closable="false" :title="result.errorMessage" />

      <section v-if="result.summary" class="summary-block">
        <h4>查询结论</h4>
        <p>{{ result.summary }}</p>
        <ul v-if="result.visualization.insights?.length">
          <li v-for="item in result.visualization.insights" :key="item">{{ item }}</li>
        </ul>
      </section>

      <section v-if="result.generatedSql" class="sql-block">
        <div class="section-title">
          <h4>已执行 SQL</h4>
          <ElButton text @click="copySql">
            <SvgIcon icon="mdi:content-copy" />
            复制
          </ElButton>
        </div>
        <pre><code>{{ result.generatedSql }}</code></pre>
        <div class="risk-row">
          <span>引用表：{{ result.referencedTables.join('、') || '-' }}</span>
          <span>预计扫描：{{ result.estimatedRows ?? '未知' }} 行</span>
          <ElTag v-if="result.fullTableScan" type="warning" size="small" effect="plain">存在全表扫描</ElTag>
        </div>
      </section>

      <section class="table-block">
        <h4>查询结果</h4>
        <ElTable :data="result.resultRows" border max-height="460" empty-text="没有匹配数据">
          <ElTableColumn
            v-for="column in result.resultColumns"
            :key="column"
            :prop="column"
            :label="column"
            min-width="150"
            show-overflow-tooltip
          >
            <template #default="{ row }">{{ renderCell(row[column]) }}</template>
          </ElTableColumn>
        </ElTable>
      </section>
    </ElCard>

    <ElEmpty v-else description="选择数据源后，用自然语言提出一个数据问题" />

    <ElDrawer
      v-model="sourceDrawerVisible"
      :title="editingSourceId ? '编辑环境数据源' : '配置环境数据源'"
      size="min(680px, 96vw)"
    >
      <ElAlert
        type="warning"
        :closable="false"
        show-icon
        title="请在 MySQL/PostgreSQL 中创建只授予 SELECT 权限的专用账号；平台校验不能替代数据库自身权限。"
      />
      <ElForm ref="sourceFormRef" :model="sourceForm" :rules="sourceRules" label-position="top" class="source-form">
        <div class="form-grid">
          <ElFormItem label="测试环境" prop="environmentId">
            <ElSelect v-model="sourceForm.environmentId" :disabled="Boolean(editingSourceId)">
              <ElOption v-for="item in environmentOptions" :key="item.value" :label="item.label" :value="item.value" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="数据源名称" prop="name">
            <ElInput v-model="sourceForm.name" placeholder="例如：博客测试库" />
          </ElFormItem>
          <ElFormItem label="数据库类型">
            <ElSelect
              v-model="sourceForm.databaseType"
              :disabled="Boolean(editingSourceId)"
              @change="applyDatabaseDefaults"
            >
              <ElOption label="MySQL" value="MYSQL" />
              <ElOption label="PostgreSQL" value="POSTGRESQL" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="主机" prop="host">
            <ElInput v-model="sourceForm.host" placeholder="127.0.0.1 或内网域名" />
          </ElFormItem>
          <ElFormItem label="端口">
            <ElInputNumber v-model="sourceForm.port" :min="1" :max="65535" controls-position="right" />
          </ElFormItem>
          <ElFormItem label="数据库名称" prop="databaseName"><ElInput v-model="sourceForm.databaseName" /></ElFormItem>
          <ElFormItem v-if="sourceForm.databaseType === 'POSTGRESQL'" label="Schema">
            <ElInput v-model="sourceForm.schemaName" placeholder="public" />
          </ElFormItem>
          <ElFormItem label="字符集"><ElInput v-model="sourceForm.charset" /></ElFormItem>
          <ElFormItem :label="editingSourceId ? '只读用户名（留空保留）' : '只读用户名'" prop="username">
            <ElInput v-model="sourceForm.username" autocomplete="off" />
          </ElFormItem>
          <ElFormItem :label="editingSourceId ? '密码（留空保留）' : '密码'">
            <ElInput v-model="sourceForm.password" type="password" show-password autocomplete="new-password" />
          </ElFormItem>
        </div>
        <ElFormItem label="允许查询的表">
          <ElInput
            v-model="sourceForm.allowedTablesText"
            type="textarea"
            :rows="4"
            placeholder="每行一个表名；留空表示允许本次结构快照中的全部表"
          />
        </ElFormItem>
        <ElFormItem label="敏感字段">
          <ElInput
            v-model="sourceForm.sensitiveColumnsText"
            type="textarea"
            :rows="4"
            placeholder="每行格式：users:password,id_card,mobile"
          />
          <div class="field-help">模型生成或用户诱导查询这些字段时，后端会在执行前拒绝。</div>
        </ElFormItem>
        <ElFormItem label="连接选项">
          <ElCheckbox v-model="sourceForm.sslEnabled">启用 SSL</ElCheckbox>
          <ElCheckbox v-model="sourceForm.enabled">允许智能查询</ElCheckbox>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="sourceDrawerVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="savingSource" @click="submitSource">保存数据源</ElButton>
      </template>
    </ElDrawer>

    <ElDrawer v-model="historyDrawerVisible" title="数据查询历史" size="min(760px, 96vw)">
      <div v-loading="loading" class="history-list">
        <button v-for="item in history" :key="item.id" type="button" class="history-item" @click="selectHistory(item)">
          <div>
            <strong>{{ item.question }}</strong>
            <small>{{ item.dataSourceName }} · {{ dayjs(item.createdAt).format('YYYY-MM-DD HH:mm:ss') }}</small>
          </div>
          <ElTag :type="statusMap[item.status].type" effect="plain" size="small">
            {{ statusMap[item.status].label }}
          </ElTag>
        </button>
        <ElEmpty v-if="!history.length" description="暂无查询历史" />
      </div>
      <ElPagination
        v-if="historyTotal > 20"
        v-model:current-page="historyCurrent"
        :page-size="20"
        :total="historyTotal"
        layout="prev, pager, next"
        @current-change="loadHistory"
      />
    </ElDrawer>
  </div>
</template>

<style scoped>
.data-query-page {
  display: grid;
  gap: 16px;
  min-height: 100%;
}
.query-card,
.result-card {
  border-radius: 10px;
}
.page-header,
.result-header,
.section-title,
.question-footer,
.source-strip,
.source-strip > div,
.header-actions,
.source-actions,
.risk-row {
  display: flex;
  align-items: center;
}
.page-header,
.result-header,
.question-footer,
.source-strip,
.section-title {
  justify-content: space-between;
  gap: 16px;
}
.page-header h3,
.summary-block h4,
.sql-block h4,
.table-block h4,
.section-title h4 {
  margin: 0;
}
.page-header p {
  margin: 5px 0 0;
  color: var(--el-text-color-secondary);
}
.header-actions,
.source-actions,
.source-strip > div,
.risk-row {
  gap: 10px;
  flex-wrap: wrap;
}
.selector-grid,
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.source-strip {
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.source-strip code {
  color: var(--el-text-color-secondary);
}
.option-hint {
  float: right;
  margin-left: 24px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.question-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
}
.question-footer {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.result-card :deep(.el-alert) {
  margin-bottom: 14px;
}
.result-header > div {
  display: flex;
  align-items: center;
  gap: 10px;
}
.result-header > span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.summary-block,
.sql-block,
.table-block {
  margin-bottom: 18px;
}
.summary-block {
  padding: 16px;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
}
.summary-block p {
  margin: 10px 0 0;
  line-height: 1.8;
  white-space: pre-wrap;
}
.summary-block ul {
  margin-bottom: 0;
  line-height: 1.8;
}
.sql-block pre {
  overflow: auto;
  margin: 8px 0;
  padding: 14px;
  color: #d7e1f4;
  background: #18212f;
  border-radius: 8px;
  line-height: 1.6;
}
.risk-row {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.executing-tip {
  margin-top: 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
.source-form {
  margin-top: 18px;
}
.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.field-help {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.history-list {
  display: grid;
  gap: 10px;
  min-height: 160px;
}
.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px;
  text-align: left;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  cursor: pointer;
}
.history-item:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.history-item div {
  min-width: 0;
}
.history-item strong,
.history-item small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-item small {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 760px) {
  .page-header,
  .result-header,
  .question-footer,
  .source-strip {
    align-items: stretch;
    flex-direction: column;
  }
  .header-actions,
  .source-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .selector-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
  .source-strip code {
    overflow-wrap: anywhere;
  }
}
</style>
