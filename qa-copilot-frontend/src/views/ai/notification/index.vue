<script setup lang="ts">
import { computed, ref } from 'vue';
import dayjs from 'dayjs';
import {
  fetchDeleteNotificationChannel,
  fetchGetNotificationChannelList,
  fetchTestNotificationChannel
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import NotificationChannelDrawer from './notification-channel-drawer.vue';

defineOptions({ name: 'NotificationChannelManage' });

type StatusFilter = 'all' | 'enabled' | 'disabled';

const authStore = useAuthStore();
const loading = ref(false);
const testingId = ref<number | null>(null);
const records = ref<Api.AIManage.NotificationChannel[]>([]);
const keyword = ref('');
const status = ref<StatusFilter>('all');
const drawerVisible = ref(false);
const operateType = ref<UI.TableOperateType>('add');
const editingData = ref<Api.AIManage.NotificationChannel | null>(null);

const permissions = computed(() => new Set(authStore.userInfo.buttons));
const canCreate = computed(() => permissions.value.has('*') || permissions.value.has('notification:create'));
const canUpdate = computed(() => permissions.value.has('*') || permissions.value.has('notification:update'));
const canDelete = computed(() => permissions.value.has('*') || permissions.value.has('notification:delete'));
const canTest = computed(() => permissions.value.has('*') || permissions.value.has('notification:test'));

const filteredRecords = computed(() => {
  const normalized = keyword.value.trim().toLowerCase();
  return records.value.filter(item => {
    const matchesKeyword =
      !normalized || `${item.name} ${typeLabel(item.channelType)}`.toLowerCase().includes(normalized);
    const matchesStatus = status.value === 'all' || item.enabled === (status.value === 'enabled');
    return matchesKeyword && matchesStatus;
  });
});

const typeLabels: Record<Api.AIManage.NotificationChannelType, string> = {
  WEBHOOK: '通用 Webhook',
  WECHAT_WORK_BOT: '企业微信群机器人',
  DINGTALK_BOT: '钉钉群机器人',
  SMTP: 'SMTP 邮件'
};

function typeLabel(type: Api.AIManage.NotificationChannelType) {
  return typeLabels[type];
}

function ruleLabel(row: Api.AIManage.NotificationChannel) {
  if (row.breakingOnly || row.importanceThreshold >= 100) return '仅失败或超时';
  if (row.importanceThreshold >= 80) return '取消及失败';
  return '所有执行结果';
}

function configSummary(row: Api.AIManage.NotificationChannel) {
  if (row.channelType === 'SMTP') {
    return `${row.config.host || '-'}:${row.config.port || '-'} · ${(row.config.recipients || []).length} 个收件人`;
  }
  return `密钥已${row.secretConfigured ? '加密配置' : '缺失'} · 超时 ${row.config.timeoutSeconds || 10}s`;
}

async function getData() {
  loading.value = true;
  const { data, error } = await fetchGetNotificationChannelList();
  loading.value = false;
  if (!error) records.value = data;
}

function handleAdd() {
  operateType.value = 'add';
  editingData.value = null;
  drawerVisible.value = true;
}

function handleEdit(row: Api.AIManage.NotificationChannel) {
  operateType.value = 'edit';
  editingData.value = row;
  drawerVisible.value = true;
}

async function handleTest(row: Api.AIManage.NotificationChannel) {
  testingId.value = row.id;
  const { data, error } = await fetchTestNotificationChannel(row.id);
  testingId.value = null;
  if (!error) window.$message?.success(`${data.message}，耗时 ${data.latencyMs} ms`);
}

async function handleDelete(row: Api.AIManage.NotificationChannel) {
  const { error } = await fetchDeleteNotificationChannel(row.id);
  if (error) return;
  window.$message?.success(`通知渠道“${row.name}”已删除`);
  await getData();
}

void getData();
</script>

<template>
  <div class="manage-table-page notification-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>通知渠道</h2>
            <p>集中管理自动化执行完成、失败和超时通知；密钥只在后端加密保存</p>
          </div>
          <div class="manage-table-header__actions">
            <ElTooltip content="刷新当前数据" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <SvgIcon icon="mdi:refresh" :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <ElButton v-if="canCreate" type="primary" @click="handleAdd">
              <template #icon><SvgIcon icon="mdi:plus" /></template>
              新增渠道
            </ElButton>
          </div>
        </div>
      </template>

      <div class="manage-table-toolbar">
        <ElInput v-model="keyword" clearable class="manage-table-search" placeholder="搜索渠道名称或类型">
          <template #prefix><SvgIcon icon="mdi:magnify" /></template>
        </ElInput>
        <ElSelect v-model="status" class="notification-status-filter">
          <ElOption label="全部状态" value="all" />
          <ElOption label="已启用" value="enabled" />
          <ElOption label="已停用" value="disabled" />
        </ElSelect>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="filteredRecords" row-key="id">
          <ElTableColumn type="index" label="序号" width="58" align="center" />
          <ElTableColumn label="通知渠道" min-width="220">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <div class="notification-identity">
                <span><SvgIcon :icon="row.channelType === 'SMTP' ? 'mdi:email-outline' : 'mdi:webhook'" /></span>
                <div>
                  <strong>{{ row.name }}</strong>
                  <small>{{ typeLabel(row.channelType) }}</small>
                </div>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="连接配置" min-width="250" show-overflow-tooltip>
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <span class="notification-secondary">{{ configSummary(row) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="发送范围" min-width="150">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <span class="notification-rule">{{ ruleLabel(row) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="密钥" width="105" align="center">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <span class="notification-secret" :class="{ 'is-ready': row.secretConfigured }">
                <SvgIcon :icon="row.secretConfigured ? 'mdi:shield-lock-outline' : 'mdi:alert-outline'" />
                {{ row.secretConfigured ? '已配置' : '未配置' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="95" align="center">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <span class="table-status" :class="[row.enabled ? 'is-enabled' : 'is-disabled']">
                <span />
                {{ row.enabled ? '启用' : '停用' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" width="160">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="142" align="right" fixed="right">
            <template #default="{ row }: { row: Api.AIManage.NotificationChannel }">
              <div class="table-row-actions">
                <ElTooltip v-if="canTest" content="发送测试通知" placement="top">
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :loading="testingId === row.id"
                    @click="handleTest(row)"
                  >
                    <SvgIcon v-if="testingId !== row.id" icon="mdi:send-check-outline" />
                  </ElButton>
                </ElTooltip>
                <ElTooltip v-if="canUpdate" content="编辑" placement="top">
                  <ElButton text circle class="table-row-action" @click="handleEdit(row)">
                    <SvgIcon icon="mdi:pencil-outline" />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm v-if="canDelete" :title="`确认删除“${row.name}”吗？`" @confirm="handleDelete(row)">
                  <template #reference>
                    <ElButton text circle class="table-row-action is-danger" title="删除">
                      <SvgIcon icon="mdi:delete-outline" />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="暂无通知渠道" :image-size="72" /></template>
        </ElTable>
      </div>

      <NotificationChannelDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getData"
      />
    </ElCard>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style scoped lang="scss">
.notification-status-filter {
  width: 160px;
}
.notification-identity {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}
.notification-identity > span {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 17px;
}
.notification-identity div {
  min-width: 0;
}
.notification-identity strong,
.notification-identity small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notification-identity strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}
.notification-identity small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.notification-secondary {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.notification-rule {
  display: inline-flex;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 5px;
  background: var(--el-color-primary-light-9);
  padding: 3px 8px;
  color: var(--el-color-primary);
  font-size: 11px;
}
.notification-secret {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--el-color-danger);
  font-size: 11px;
}
.notification-secret.is-ready {
  color: var(--el-color-success);
}

@media (max-width: 700px) {
  .notification-status-filter {
    width: 100%;
  }
  :deep(.manage-table-toolbar) {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
