<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useDebounceFn, useMediaQuery } from '@vueuse/core';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCreateTestEnvironment,
  fetchDeleteTestEnvironment,
  fetchGetProjectList,
  fetchGetTestEnvironments,
  fetchTestEnvironmentConnection,
  fetchUpdateTestEnvironment
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'ProjectEnvironments' });

type EnvironmentStatusFilter = 'all' | 'enabled' | 'disabled';
type HeaderRow = { key: string; value: string };

const route = useRoute();
const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const projectLoading = ref(false);
const submitting = ref(false);
const keyword = ref('');
const status = ref<EnvironmentStatusFilter>('all');
const drawerVisible = ref(false);
const editingId = ref<number | null>(null);
const testingId = ref<number | null>(null);
const togglingId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const environments = ref<Api.ProjectManage.TestEnvironment[]>([]);
const formRef = ref<FormInstance>();
const form = reactive({
  name: '',
  environmentType: 'TEST' as Api.ProjectManage.TestEnvironmentType,
  baseUrl: '',
  allowedHostsText: '',
  enabled: true,
  headers: [] as HeaderRow[],
  variables: [] as Api.ProjectManage.TestEnvironmentVariable[]
});

const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const activeProject = computed(() => projects.value.find(item => item.id === activeProjectId.value));
const isArchivedProject = computed(() => activeProject.value?.status === 'ARCHIVED');
const canManageEnvironments = computed(() => hasPermission('project:environment:manage'));
const canTestEnvironments = computed(() => hasPermission('project:environment:test'));

const environmentTypeOptions: Array<{ label: string; value: Api.ProjectManage.TestEnvironmentType }> = [
  { label: '本地', value: 'LOCAL' },
  { label: '开发', value: 'DEVELOPMENT' },
  { label: '测试', value: 'TEST' },
  { label: '预发布', value: 'STAGING' },
  { label: '生产（禁止自动化执行）', value: 'PRODUCTION' }
];

const rules: FormRules = {
  name: [{ required: true, message: '请输入环境名称', trigger: 'blur' }],
  environmentType: [{ required: true, message: '请选择环境类型', trigger: 'change' }],
  baseUrl: [
    { required: true, message: '请输入基础地址', trigger: 'blur' },
    { type: 'url', message: '请输入完整的 HTTP(S) 地址', trigger: 'blur' }
  ],
  allowedHostsText: [{ required: true, message: '请至少配置一个允许访问的域名', trigger: 'blur' }]
};

function hasPermission(code: string) {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes(code);
}

async function getProjects() {
  projectLoading.value = true;
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  projectLoading.value = false;
  if (error) return;

  projects.value = data.records;
  // 自动化执行页跳转过来时优先选中原项目，用户无需再次寻找项目。
  const routeProjectId = Number(route.query.projectId) || null;
  if (routeProjectId && projects.value.some(item => item.id === routeProjectId)) {
    activeProjectId.value = routeProjectId;
    return;
  }
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

function getEnabledParam() {
  if (status.value === 'all') return undefined;
  return status.value === 'enabled';
}

async function getData() {
  if (!activeProjectId.value) {
    environments.value = [];
    return;
  }

  loading.value = true;
  const { data, error } = await fetchGetTestEnvironments(activeProjectId.value, {
    keyword: keyword.value.trim(),
    enabled: getEnabledParam()
  });
  loading.value = false;
  if (!error) environments.value = data;
}

async function handleProjectChange() {
  keyword.value = '';
  status.value = 'all';
  await getData();
}

const handleFilterChange = useDebounceFn(getData, 300);

async function openDrawer(row?: Api.ProjectManage.TestEnvironment) {
  if (!activeProjectId.value) {
    window.$message?.warning('请先选择项目');
    return;
  }
  if (isArchivedProject.value) {
    window.$message?.warning('已归档项目不能管理测试环境');
    return;
  }

  editingId.value = row?.id ?? null;
  Object.assign(
    form,
    row
      ? {
          name: row.name,
          environmentType: row.environmentType,
          baseUrl: row.baseUrl,
          allowedHostsText: row.allowedHosts.join('\n'),
          enabled: row.enabled,
          headers: Object.entries(row.headers).map(([key, value]) => ({ key, value })),
          variables: row.variables.map(item => ({ ...item }))
        }
      : {
          name: '',
          environmentType: 'TEST',
          baseUrl: '',
          allowedHostsText: '',
          enabled: true,
          headers: [],
          variables: []
        }
  );
  drawerVisible.value = true;
  await nextTick();
  formRef.value?.clearValidate();
}

function addHeader() {
  form.headers.push({ key: '', value: '' });
}

function removeHeader(index: number) {
  form.headers.splice(index, 1);
}

function addVariable() {
  form.variables.push({ key: '', value: '', secret: true });
}

function removeVariable(index: number) {
  form.variables.splice(index, 1);
}

function parseAllowedHosts() {
  return [
    ...new Set(
      form.allowedHostsText
        .split(/[\n,]/)
        .map(item => item.trim().toLowerCase())
        .filter(Boolean)
    )
  ];
}

function buildHeaders() {
  const rows = form.headers.map(item => ({ key: item.key.trim(), value: item.value.trim() }));
  if (rows.some(item => !item.key)) {
    window.$message?.warning('请求头名称不能为空');
    return null;
  }
  const normalizedKeys = rows.map(item => item.key.toLowerCase());
  if (new Set(normalizedKeys).size !== normalizedKeys.length) {
    window.$message?.warning('请求头名称不能重复');
    return null;
  }
  return Object.fromEntries(rows.map(item => [item.key, item.value]));
}

function buildVariables() {
  const rows = form.variables.map(item => ({ ...item, key: item.key.trim() }));
  if (rows.some(item => !/^[A-Za-z_][A-Za-z0-9_.-]*$/.test(item.key))) {
    window.$message?.warning('变量名须以字母或下划线开头，只能包含字母、数字、点、短横线和下划线');
    return null;
  }
  if (new Set(rows.map(item => item.key)).size !== rows.length) {
    window.$message?.warning('环境变量名称不能重复');
    return null;
  }
  return rows;
}

function validateHostBoundary(allowedHosts: string[]) {
  if (allowedHosts.includes('*') && allowedHosts.length > 1) {
    window.$message?.warning('* 代表所有公网域名，不能和其他域名一起配置');
    return false;
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(form.baseUrl);
  } catch {
    window.$message?.warning('基础地址格式不正确');
    return false;
  }
  if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
    window.$message?.warning('基础地址只支持 HTTP 或 HTTPS');
    return false;
  }

  const baseHost = parsedUrl.hostname.toLowerCase().replace(/\.$/, '');
  if (!allowedHosts.includes('*') && !allowedHosts.includes(baseHost)) {
    window.$message?.warning(`基础地址域名 ${baseHost} 必须加入域名白名单`);
    return false;
  }
  return true;
}

async function submitForm() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !activeProjectId.value) return;

  const allowedHosts = parseAllowedHosts();
  const headers = buildHeaders();
  const variables = buildVariables();
  if (!headers || !variables || !validateHostBoundary(allowedHosts)) return;

  const payload: Api.ProjectManage.TestEnvironmentCreateParams = {
    name: form.name.trim(),
    environmentType: form.environmentType,
    baseUrl: form.baseUrl.trim().replace(/\/$/, ''),
    allowedHosts,
    headers,
    variables,
    enabled: form.enabled
  };

  submitting.value = true;
  const { error } = editingId.value
    ? await fetchUpdateTestEnvironment(activeProjectId.value, editingId.value, payload)
    : await fetchCreateTestEnvironment(activeProjectId.value, payload);
  submitting.value = false;
  if (error) return;

  drawerVisible.value = false;
  window.$message?.success(editingId.value ? '测试环境已更新' : '测试环境已创建');
  await getData();
}

async function deleteEnvironment(row: Api.ProjectManage.TestEnvironment) {
  if (!activeProjectId.value) return;
  const { error } = await fetchDeleteTestEnvironment(activeProjectId.value, row.id);
  if (error) return;

  window.$message?.success('测试环境已删除');
  await getData();
}

async function toggleEnvironment(row: Api.ProjectManage.TestEnvironment, enabled: string | number | boolean) {
  if (!activeProjectId.value || typeof enabled !== 'boolean') return;

  togglingId.value = row.id;
  const { error } = await fetchUpdateTestEnvironment(activeProjectId.value, row.id, { enabled });
  togglingId.value = null;
  if (error) {
    row.enabled = !enabled;
    return;
  }
  window.$message?.success(enabled ? '环境已启用' : '环境已停用');
  await getData();
}

async function testConnection(row: Api.ProjectManage.TestEnvironment) {
  if (!activeProjectId.value) return;

  testingId.value = row.id;
  const { data, error } = await fetchTestEnvironmentConnection(activeProjectId.value, row.id);
  testingId.value = null;
  if (error) return;

  const detail = data.statusCode ? `HTTP ${data.statusCode}，${data.latencyMs} ms` : `${data.latencyMs} ms`;
  if (data.success) window.$message?.success(`${data.message}（${detail}）`);
  else window.$message?.warning(`${data.message}（${detail}）`);
}

async function initialize() {
  await getProjects();
  await getData();
}

initialize();
</script>

<template>
  <div class="project-page manage-table-page">
    <ElCard class="project-card manage-table-card">
      <template #header>
        <div class="project-page-header">
          <div class="project-page-title">
            <h2>测试环境</h2>
            <p>维护接口自动化地址、域名白名单与加密变量，限制任务访问边界</p>
          </div>
          <div class="project-page-actions">
            <ElButton
              v-if="canManageEnvironments"
              type="primary"
              :disabled="!activeProjectId || isArchivedProject"
              @click="openDrawer()"
            >
              <template #icon><icon-ic-round-plus /></template>
              新建环境
            </ElButton>
          </div>
        </div>
      </template>

      <div class="project-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-selector"
          placeholder="选择项目"
          :loading="projectLoading"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElInput
          v-model="keyword"
          clearable
          class="project-search"
          placeholder="搜索环境名称、地址或白名单"
          @input="handleFilterChange"
          @clear="getData"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElSelect v-model="status" class="environment-status-filter" @change="getData">
          <ElOption label="全部状态" value="all" />
          <ElOption label="已启用" value="enabled" />
          <ElOption label="已停用" value="disabled" />
        </ElSelect>
      </div>

      <div v-if="!isMobile" v-loading="loading" class="manage-table-body">
        <ElTable height="100%" border class="mx-data-table" :data="environments" row-key="id">
          <ElTableColumn label="环境" min-width="210">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <div class="project-name-cell">
                <span class="project-name-icon"><SvgIcon icon="mdi:server-network-outline" /></span>
                <span class="project-name-copy">
                  <strong>{{ row.name }}</strong>
                  <small>{{ row.createdByName || '未知创建人' }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="基础地址" min-width="250" show-overflow-tooltip>
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <code class="project-code">{{ row.baseUrl }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn label="类型" width="96" align="center">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <ElTag :type="row.environmentType === 'PRODUCTION' ? 'danger' : 'info'" effect="plain">
                {{ environmentTypeOptions.find(item => item.value === row.environmentType)?.label }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="域名白名单" min-width="210">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <div class="host-list">
                <ElTag v-for="host in row.allowedHosts.slice(0, 2)" :key="host" size="small" effect="plain" type="info">
                  {{ host }}
                </ElTag>
                <ElTag v-if="row.allowedHosts.length > 2" size="small" effect="plain" type="info">
                  +{{ row.allowedHosts.length - 2 }}
                </ElTag>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="变量" width="82" align="center">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <span class="project-secondary">{{ row.variableCount }} 项</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="启用" width="78" align="center">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <ElSwitch
                v-model="row.enabled"
                :loading="togglingId === row.id"
                :disabled="!canManageEnvironments || isArchivedProject"
                @change="value => toggleEnvironment(row, value)"
              />
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" min-width="150">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="142" align="right" fixed="right">
            <template #default="{ row }: { row: Api.ProjectManage.TestEnvironment }">
              <div class="table-row-actions">
                <ElTooltip v-if="canTestEnvironments" content="测试连接" placement="top">
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :loading="testingId === row.id"
                    :disabled="!row.enabled || isArchivedProject"
                    @click="testConnection(row)"
                  >
                    <SvgIcon v-if="testingId !== row.id" icon="mdi:connection" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip v-if="canManageEnvironments" content="编辑" placement="top">
                  <ElButton text circle class="table-row-action" :disabled="isArchivedProject" @click="openDrawer(row)">
                    <icon-material-symbols-edit-outline-rounded />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm
                  v-if="canManageEnvironments"
                  title="确认删除该测试环境？"
                  @confirm="deleteEnvironment(row)"
                >
                  <template #reference>
                    <ElButton text circle class="table-row-action is-danger" :disabled="isArchivedProject">
                      <icon-ic-round-delete />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前项目暂无测试环境" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else v-loading="loading" class="environment-mobile-list">
        <div v-for="row in environments" :key="row.id" class="environment-mobile-card">
          <div class="environment-mobile-head">
            <div class="project-name-cell">
              <span class="project-name-icon"><SvgIcon icon="mdi:server-network-outline" /></span>
              <span class="project-name-copy">
                <strong>{{ row.name }}</strong>
                <small>
                  {{ environmentTypeOptions.find(item => item.value === row.environmentType)?.label }} ·
                  {{ row.enabled ? '已启用' : '已停用' }} · {{ row.variableCount }} 个变量
                </small>
              </span>
            </div>
            <ElSwitch
              v-if="canManageEnvironments"
              v-model="row.enabled"
              :loading="togglingId === row.id"
              :disabled="isArchivedProject"
              @change="value => toggleEnvironment(row, value)"
            />
            <ElTag v-else size="small" :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '启用' : '停用' }}
            </ElTag>
          </div>
          <code class="environment-mobile-url">{{ row.baseUrl }}</code>
          <div class="host-list">
            <ElTag v-for="host in row.allowedHosts" :key="host" size="small" effect="plain" type="info">
              {{ host }}
            </ElTag>
          </div>
          <div class="environment-mobile-foot">
            <span>{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            <div class="table-row-actions">
              <ElButton
                v-if="canTestEnvironments"
                text
                size="small"
                :loading="testingId === row.id"
                :disabled="!row.enabled || isArchivedProject"
                @click="testConnection(row)"
              >
                测试
              </ElButton>
              <ElButton
                v-if="canManageEnvironments"
                text
                size="small"
                :disabled="isArchivedProject"
                @click="openDrawer(row)"
              >
                编辑
              </ElButton>
              <ElPopconfirm v-if="canManageEnvironments" title="确认删除该测试环境？" @confirm="deleteEnvironment(row)">
                <template #reference>
                  <ElButton text size="small" type="danger" :disabled="isArchivedProject">删除</ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </div>
        </div>
        <ElEmpty v-if="!environments.length" description="当前项目暂无测试环境" :image-size="72" />
      </div>
    </ElCard>

    <ElDrawer
      v-model="drawerVisible"
      :title="editingId ? '编辑测试环境' : '新建测试环境'"
      size="min(640px, 94vw)"
      destroy-on-close
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="环境名称" prop="name">
          <ElInput v-model="form.name" maxlength="120" placeholder="例如：SIT 测试环境" />
        </ElFormItem>
        <ElFormItem label="环境类型" prop="environmentType">
          <ElSelect v-model="form.environmentType" placeholder="请选择环境类型">
            <ElOption
              v-for="item in environmentTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </ElSelect>
          <div class="field-help">生产环境可用于配置管理和连接测试，但自动化执行器会在后端强制拒绝。</div>
        </ElFormItem>
        <ElFormItem label="基础地址" prop="baseUrl">
          <ElInput v-model="form.baseUrl" maxlength="1000" placeholder="https://sit-api.example.internal" />
        </ElFormItem>
        <ElFormItem label="域名白名单" prop="allowedHostsText">
          <ElInput
            v-model="form.allowedHostsText"
            type="textarea"
            :rows="3"
            placeholder="每行一个域名，不包含协议、端口和路径"
          />
          <div class="field-help">基础地址的域名必须在白名单中；超级管理员可单独填写 * 允许所有公网域名。</div>
        </ElFormItem>
        <ElFormItem label="启用状态">
          <ElSwitch v-model="form.enabled" active-text="允许自动化任务使用" />
        </ElFormItem>

        <div class="config-section-header">
          <div>
            <strong>公共请求头</strong>
            <p>
              每次请求都会携带；敏感值建议写成
              <code v-pre>{{ api_token }}</code>
              引用加密变量
            </p>
          </div>
          <ElButton @click="addHeader">
            <template #icon><icon-ic-round-plus /></template>
            添加请求头
          </ElButton>
        </div>
        <div v-if="form.headers.length" class="config-list">
          <div v-for="(header, index) in form.headers" :key="index" class="header-row">
            <ElInput v-model="header.key" placeholder="请求头，例如 Authorization" />
            <ElInput v-model="header.value" placeholder="值，例如 Bearer {{api_token}}" />
            <ElButton text circle class="table-row-action is-danger" @click="removeHeader(index)">
              <icon-ic-round-delete />
            </ElButton>
          </div>
        </div>
        <div v-else class="config-empty">暂无公共请求头</div>

        <div class="config-section-header">
          <div>
            <strong>环境变量</strong>
            <p>敏感值会加密保存，编辑时显示 ******** 仅表示保留原值</p>
          </div>
          <ElButton @click="addVariable">
            <template #icon><icon-ic-round-plus /></template>
            添加变量
          </ElButton>
        </div>
        <div v-if="form.variables.length" class="config-list">
          <div v-for="(variable, index) in form.variables" :key="index" class="variable-row">
            <ElInput v-model="variable.key" maxlength="120" placeholder="变量名" />
            <ElInput
              v-model="variable.value"
              :type="variable.secret ? 'password' : 'text'"
              maxlength="10000"
              placeholder="变量值"
              show-password
            />
            <ElCheckbox v-model="variable.secret" :disabled="variable.value === '********'">加密</ElCheckbox>
            <ElButton text circle class="table-row-action is-danger" @click="removeVariable(index)">
              <icon-ic-round-delete />
            </ElButton>
          </div>
        </div>
        <div v-else class="config-empty">暂无环境变量</div>
      </ElForm>
      <template #footer>
        <ElButton @click="drawerVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">保存环境</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.environment-status-filter {
  width: 132px;
}
.host-list {
  display: flex;
  overflow: hidden;
  flex-wrap: wrap;
  gap: 5px;
}
.field-help {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.config-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20px 0 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 18px;
  gap: 12px;
}
.config-section-header strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}
.config-section-header p {
  margin: 3px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.config-section-header code {
  color: rgb(var(--primary-color));
}
.config-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.config-empty {
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  padding: 14px;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  text-align: center;
}
.header-row,
.variable-row {
  display: grid;
  align-items: center;
  gap: 8px;
}
.header-row {
  grid-template-columns: 1fr 1.5fr 30px;
}
.variable-row {
  grid-template-columns: 1fr 1.4fr 68px 30px;
}
.environment-mobile-list {
  min-height: 280px;
  padding: 10px;
}
.environment-mobile-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 12px;
}
.environment-mobile-card + .environment-mobile-card {
  margin-top: 10px;
}
.environment-mobile-head,
.environment-mobile-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.environment-mobile-url {
  display: block;
  overflow: hidden;
  margin: 10px 0 8px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.environment-mobile-foot {
  margin-top: 10px;
  border-top: 1px solid var(--el-border-color-extra-light);
  padding-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
@media (max-width: 700px) {
  .environment-status-filter {
    width: 100%;
  }
  .config-section-header {
    align-items: stretch;
    flex-direction: column;
  }
  .header-row,
  .variable-row {
    grid-template-columns: 1fr;
    border-bottom: 1px solid var(--el-border-color-lighter);
    padding-bottom: 12px;
  }
  .environment-mobile-foot .table-row-actions {
    gap: 0;
  }
}
</style>
