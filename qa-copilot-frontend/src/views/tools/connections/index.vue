<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import dayjs from 'dayjs';
import {
  fetchCreateToolConnection,
  fetchDeleteToolConnection,
  fetchGetToolConnections,
  fetchUpdateToolConnection
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import ProjectSelector from '../components/project-selector.vue';

defineOptions({ name: 'ToolsConnections' });
const authStore = useAuthStore();
const projectId = ref<number | null>(null);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const editing = ref<Api.ToolManage.Connection | null>(null);
const records = ref<Api.ToolManage.Connection[]>([]);
const form = reactive({
  name: '',
  type: 'MYSQL' as Api.ToolManage.ConnectionType,
  host: '',
  port: 3306,
  database: '',
  baseUrl: '',
  namespace: '',
  createPath: '/api/defects',
  projectKey: '',
  username: '',
  password: '',
  token: '',
  enabled: true
});
const canManage = computed(
  () => authStore.userInfo.buttons.includes('*') || authStore.userInfo.buttons.includes('tool:manage')
);
const typeLabels: Record<Api.ToolManage.ConnectionType, string> = {
  MYSQL: 'MySQL 数据库',
  NACOS: 'Nacos 配置中心',
  BUSINESS_API: '业务接口',
  DEFECT_PLATFORM: '缺陷平台'
};

async function loadData() {
  if (!projectId.value) return;
  loading.value = true;
  const { data, error } = await fetchGetToolConnections(projectId.value);
  loading.value = false;
  if (!error) records.value = data;
}
function resetForm(row?: Api.ToolManage.Connection) {
  editing.value = row ?? null;
  Object.assign(form, {
    name: row?.name ?? '',
    type: row?.connectionType ?? 'MYSQL',
    host: row?.config.host ?? '',
    port: row?.config.port ?? (row?.connectionType === 'NACOS' ? 8848 : 3306),
    database: row?.config.database ?? '',
    baseUrl: row?.config.baseUrl ?? '',
    namespace: row?.config.namespace ?? '',
    createPath: row?.config.createPath ?? '/api/defects',
    projectKey: row?.config.projectKey ?? '',
    username: '',
    password: '',
    token: '',
    enabled: row?.enabled ?? true
  });
  visible.value = true;
}
function configPayload() {
  if (form.type === 'MYSQL')
    return {
      host: form.host.trim(),
      port: form.port,
      database: form.database.trim(),
      charset: 'utf8mb4',
      timeoutSeconds: 10
    };
  if (form.type === 'DEFECT_PLATFORM')
    return {
      baseUrl: form.baseUrl.trim(),
      createPath: form.createPath.trim() || '/api/defects',
      projectKey: form.projectKey.trim(),
      timeoutSeconds: 10
    };
  return { baseUrl: form.baseUrl.trim(), namespace: form.namespace.trim(), timeoutSeconds: 10 };
}
function credentialPayload() {
  const value: Record<string, string> = {};
  if (form.username.trim()) value.username = form.username.trim();
  if (form.password) value.password = form.password;
  if (form.token) value.token = form.token;
  return value;
}
async function save() {
  if (!projectId.value || !form.name.trim()) return window.$message?.warning('请填写连接名称');
  saving.value = true;
  const credentials = credentialPayload();
  const common = { name: form.name.trim(), config: configPayload(), enabled: form.enabled };
  const result = editing.value
    ? await fetchUpdateToolConnection(projectId.value, editing.value.id, {
        ...common,
        ...(Object.keys(credentials).length ? { credentials } : {})
      })
    : await fetchCreateToolConnection(projectId.value, { ...common, credentials, connectionType: form.type });
  saving.value = false;
  if (result.error) return;
  visible.value = false;
  window.$message?.success(editing.value ? '连接已更新' : '连接已创建');
  await loadData();
}
async function remove(row: Api.ToolManage.Connection) {
  if (!projectId.value) return;
  const { error } = await fetchDeleteToolConnection(projectId.value, row.id);
  if (!error) {
    window.$message?.success('连接已删除');
    await loadData();
  }
}
watch(projectId, loadData);
onMounted(loadData);
</script>

<template>
  <div class="tool-page">
    <ElCard class="tool-card">
      <template #header>
        <div class="tool-heading">
          <div>
            <h2>外部连接</h2>
            <p>公开地址与加密凭据分离；查询接口永远不返回密码和令牌原文</p>
          </div>
          <div class="tool-actions">
            <ProjectSelector v-model="projectId" />
            <ElButton v-if="canManage" type="primary" @click="resetForm()">
              <SvgIcon icon="mdi:plus" />
              新增连接
            </ElButton>
          </div>
        </div>
      </template>
      <ElTable v-loading="loading" border :data="records" row-key="id">
        <ElTableColumn label="连接" min-width="220">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <div class="connection-sub">{{ typeLabels[row.connectionType as Api.ToolManage.ConnectionType] }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="地址" min-width="240">
          <template #default="{ row }">
            <code class="tool-code">
              {{
                row.config.baseUrl || `${row.config.host || '-'}:${row.config.port || '-'}/${row.config.database || ''}`
              }}
            </code>
          </template>
        </ElTableColumn>
        <ElTableColumn label="凭据" width="110" align="center">
          <template #default="{ row }">
            <ElTag :type="row.credentialsConfigured ? 'success' : 'warning'">
              {{ row.credentialsConfigured ? '已加密配置' : '未配置' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="更新时间" width="160">
          <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
        </ElTableColumn>
        <ElTableColumn v-if="canManage" label="操作" width="115" fixed="right" align="center">
          <template #default="{ row }">
            <ElButton text circle @click="resetForm(row)"><SvgIcon icon="mdi:pencil-outline" /></ElButton>
            <ElPopconfirm :title="`删除连接“${row.name}”？`" @confirm="remove(row)">
              <template #reference>
                <ElButton text circle type="danger"><SvgIcon icon="mdi:delete-outline" /></ElButton>
              </template>
            </ElPopconfirm>
          </template>
        </ElTableColumn>
        <template #empty><ElEmpty class="tool-empty" description="当前项目暂无外部连接" /></template>
      </ElTable>
    </ElCard>
    <ElDrawer v-model="visible" :size="560" :title="editing ? '编辑外部连接' : '新增外部连接'">
      <ElAlert type="info" :closable="false" title="密钥安全">
        编辑时用户名、密码和令牌留空，会继续使用数据库中已有的密文。
      </ElAlert>
      <ElForm label-position="top" class="connection-form">
        <ElFormItem label="连接名称" required><ElInput v-model="form.name" maxlength="120" /></ElFormItem>
        <ElFormItem label="连接类型" required>
          <ElSelect v-model="form.type" class="w-full" :disabled="Boolean(editing)">
            <ElOption v-for="(label, value) in typeLabels" :key="value" :label="label" :value="value" />
          </ElSelect>
        </ElFormItem>
        <template v-if="form.type === 'MYSQL'">
          <div class="connection-grid">
            <ElFormItem label="主机名" required>
              <ElInput v-model="form.host" placeholder="mysql.internal" />
            </ElFormItem>
            <ElFormItem label="端口">
              <ElInputNumber v-model="form.port" :min="1" :max="65535" class="w-full" />
            </ElFormItem>
          </div>
          <ElFormItem label="数据库" required><ElInput v-model="form.database" /></ElFormItem>
        </template>
        <template v-else>
          <ElFormItem label="服务地址" required>
            <ElInput v-model="form.baseUrl" placeholder="https://nacos.example.com" />
          </ElFormItem>
          <template v-if="form.type === 'DEFECT_PLATFORM'">
            <ElFormItem label="创建缺陷路径">
              <ElInput v-model="form.createPath" placeholder="/api/defects" />
            </ElFormItem>
            <ElFormItem label="外部项目编码"><ElInput v-model="form.projectKey" placeholder="例如 QA" /></ElFormItem>
          </template>
          <ElFormItem v-else label="命名空间"><ElInput v-model="form.namespace" /></ElFormItem>
        </template>
        <div class="connection-grid">
          <ElFormItem label="用户名"><ElInput v-model="form.username" autocomplete="off" /></ElFormItem>
          <ElFormItem label="密码">
            <ElInput v-model="form.password" type="password" show-password autocomplete="new-password" />
          </ElFormItem>
        </div>
        <ElFormItem label="访问令牌（按需）">
          <ElInput v-model="form.token" type="password" show-password autocomplete="new-password" />
        </ElFormItem>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="visible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" scoped lang="scss"></style>

<style scoped lang="scss">
.connection-sub {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.connection-form {
  margin-top: 18px;
}
.connection-grid {
  display: grid;
  grid-template-columns: 1fr 150px;
  gap: 12px;
}
@media (max-width: 600px) {
  .connection-grid {
    grid-template-columns: 1fr;
  }
}
</style>
