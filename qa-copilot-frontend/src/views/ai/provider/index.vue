<script setup lang="tsx">
import { computed, ref } from 'vue';
import dayjs from 'dayjs';
import { fetchDeleteAIProvider, fetchGetAIProviderList } from '@/service/api';
import { $t } from '@/locales';
import ProviderOperateDrawer from './provider-operate-drawer.vue';

defineOptions({ name: 'AIProviderManage' });

const loading = ref(false);
const records = ref<Api.AIManage.Provider[]>([]);
const keyword = ref('');
const status = ref<'all' | 'enabled' | 'disabled'>('all');
const drawerVisible = ref(false);
const operateType = ref<UI.TableOperateType>('add');
const editingData = ref<Api.AIManage.Provider | null>(null);

const filteredRecords = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase();

  return records.value.filter(item => {
    const matchesKeyword =
      !normalizedKeyword ||
      [item.name, item.providerType, item.baseUrl].some(value => value?.toLowerCase().includes(normalizedKeyword));
    const matchesStatus = status.value === 'all' || item.enabled === (status.value === 'enabled');

    return matchesKeyword && matchesStatus;
  });
});

function getProviderTypeLabel(type: Api.AIManage.ProviderType) {
  return $t(`page.ai.provider.type.${type === 'openai_responses' ? 'responses' : 'compatible'}`);
}

async function getData() {
  loading.value = true;
  const { data, error } = await fetchGetAIProviderList();
  loading.value = false;

  if (!error) records.value = data;
}

function handleAdd() {
  operateType.value = 'add';
  editingData.value = null;
  drawerVisible.value = true;
}

function handleEdit(row: Api.AIManage.Provider) {
  operateType.value = 'edit';
  editingData.value = row;
  drawerVisible.value = true;
}

async function handleDelete(id: number) {
  const { error } = await fetchDeleteAIProvider(id);
  if (error) return;

  window.$message?.success($t('common.deleteSuccess'));
  await getData();
}

getData();
</script>

<template>
  <div class="manage-table-page ai-list-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>{{ $t('page.ai.provider.title') }}</h2>
            <p>{{ $t('page.manage.common.total') }} {{ filteredRecords.length }}</p>
          </div>
          <div class="manage-table-header__actions">
            <ElTooltip :content="$t('common.refresh')" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <icon-mdi-refresh :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <ElButton type="primary" @click="handleAdd">
              <template #icon><icon-ic-round-plus /></template>
              {{ $t('common.add') }}
            </ElButton>
          </div>
        </div>
      </template>

      <div class="manage-table-toolbar">
        <ElInput
          v-model="keyword"
          clearable
          class="manage-table-search"
          :placeholder="$t('page.ai.provider.searchPlaceholder')"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElSelect v-model="status" class="ai-status-filter">
          <ElOption :label="$t('page.manage.common.allStatus')" value="all" />
          <ElOption :label="$t('page.manage.common.status.enable')" value="enabled" />
          <ElOption :label="$t('page.manage.common.status.disable')" value="disabled" />
        </ElSelect>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="filteredRecords" row-key="id">
          <ElTableColumn type="index" :label="$t('common.index')" width="58" align="center" />
          <ElTableColumn :label="$t('page.ai.provider.name')" min-width="210">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <div class="ai-identity-cell">
                <span class="ai-identity-icon"><icon-material-symbols-lan-outline-rounded /></span>
                <span class="ai-identity-copy">
                  <strong>{{ row.name }}</strong>
                  <small>{{ getProviderTypeLabel(row.providerType) }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.provider.baseUrl')" min-width="260" show-overflow-tooltip>
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <code class="ai-code">{{ row.baseUrl || $t('page.ai.provider.defaultEndpoint') }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.provider.apiKey')" min-width="150">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <code class="ai-code">{{ row.apiKeyMasked || '-' }}</code>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.provider.requestPolicy')" min-width="150">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <span class="ai-secondary">{{ row.timeoutSeconds }}s · {{ row.maxRetries }}x</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.manage.user.userStatus')" width="100" align="center">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <span class="table-status" :class="[row.enabled ? 'is-enabled' : 'is-disabled']">
                <span />
                {{ $t(row.enabled ? 'page.manage.common.status.enable' : 'page.manage.common.status.disable') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.manage.common.updatedAt')" min-width="160">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('common.operate')" width="112" align="right" fixed="right">
            <template #default="{ row }: { row: Api.AIManage.Provider }">
              <div class="table-row-actions">
                <ElTooltip :content="$t('common.edit')" placement="top">
                  <ElButton text circle class="table-row-action" @click="handleEdit(row)">
                    <icon-material-symbols-edit-outline-rounded />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm :title="$t('common.confirmDelete')" @confirm="handleDelete(row.id)">
                  <template #reference>
                    <ElButton
                      text
                      circle
                      class="table-row-action is-danger"
                      :aria-label="$t('common.delete')"
                      :title="$t('common.delete')"
                    >
                      <icon-ic-round-delete />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty>
            <ElEmpty :description="$t('common.noData')" :image-size="72" />
          </template>
        </ElTable>
      </div>

      <ProviderOperateDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getData"
      />
    </ElCard>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>
