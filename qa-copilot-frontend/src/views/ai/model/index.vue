<script setup lang="tsx">
import { computed, ref } from 'vue';
import dayjs from 'dayjs';
import { fetchDeleteAIModel, fetchGetAIModelList, fetchTestAIModelConnection } from '@/service/api';
import { $t } from '@/locales';
import ModelOperateDrawer from './model-operate-drawer.vue';

defineOptions({ name: 'AIModelManage' });

const loading = ref(false);
const records = ref<Api.AIManage.Model[]>([]);
const keyword = ref('');
const status = ref<'all' | 'enabled' | 'disabled'>('all');
const drawerVisible = ref(false);
const operateType = ref<UI.TableOperateType>('add');
const editingData = ref<Api.AIManage.Model | null>(null);
const testingId = ref<number | null>(null);

const filteredRecords = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase();

  return records.value.filter(item => {
    const matchesKeyword =
      !normalizedKeyword ||
      [item.name, item.modelId, item.providerName].some(value => value.toLowerCase().includes(normalizedKeyword));
    const matchesStatus = status.value === 'all' || item.enabled === (status.value === 'enabled');

    return matchesKeyword && matchesStatus;
  });
});

async function getData() {
  loading.value = true;
  const { data, error } = await fetchGetAIModelList();
  loading.value = false;

  if (!error) records.value = data;
}

function handleAdd() {
  operateType.value = 'add';
  editingData.value = null;
  drawerVisible.value = true;
}

function handleEdit(row: Api.AIManage.Model) {
  operateType.value = 'edit';
  editingData.value = row;
  drawerVisible.value = true;
}

async function handleDelete(id: number) {
  const { error } = await fetchDeleteAIModel(id);
  if (error) return;

  window.$message?.success($t('common.deleteSuccess'));
  await getData();
}

async function handleTest(row: Api.AIManage.Model) {
  testingId.value = row.id;
  const { data, error } = await fetchTestAIModelConnection({
    modelId: row.id,
    prompt: $t('page.ai.model.testPrompt')
  });
  testingId.value = null;
  if (error) return;

  window.$message?.success({
    message: `${data.content}，${$t('page.ai.model.latency')}：${data.latencyMs} ms`,
    duration: 5000,
    showClose: true
  });
}

/**
 * 把数据库保存的任务类型编码转换为当前界面的中文或英文名称。
 * 列表同时展示名称和编码：名称方便业务人员理解，编码方便开发人员排查配置。
 * 未知的自定义编码直接原样返回，避免新增任务类型后页面显示为空。
 */
function getTaskTypeLabel(taskType: string) {
  const taskTypeLabels: Record<string, string> = {
    test_case_generation: $t('page.ai.model.taskTypeOptions.testCase'),
    test_review: $t('page.ai.model.taskTypeOptions.review'),
    defect_analysis: $t('page.ai.model.taskTypeOptions.defect'),
    knowledge_qa: $t('page.ai.model.taskTypeOptions.qa'),
    query_rewrite: $t('page.ai.model.taskTypeOptions.queryRewrite'),
    requirement_analysis: $t('page.ai.model.taskTypeOptions.requirementAnalysis'),
    coverage_analysis: $t('page.ai.model.taskTypeOptions.coverageAnalysis'),
    supervisor_planning: $t('page.ai.model.taskTypeOptions.supervisorPlanning'),
    embedding: $t('page.ai.model.taskTypeOptions.embedding'),
    rerank: $t('page.ai.model.taskTypeOptions.rerank')
  };

  const label = taskTypeLabels[taskType];
  return label ? `${label}（${taskType}）` : taskType;
}

/** 将后端保存的推理强度编码转换为当前语言的显示名称。 */
function getReasoningEffortLabel(reasoningEffort: string | null) {
  if (!reasoningEffort) return '-';

  const labels: Record<string, string> = {
    minimal: $t('page.ai.model.reasoningEffortOptions.minimal'),
    low: $t('page.ai.model.reasoningEffortOptions.low'),
    medium: $t('page.ai.model.reasoningEffortOptions.medium'),
    high: $t('page.ai.model.reasoningEffortOptions.high')
  };

  return labels[reasoningEffort] ?? reasoningEffort;
}

getData();
</script>

<template>
  <div class="manage-table-page ai-list-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>{{ $t('page.ai.model.title') }}</h2>
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
          :placeholder="$t('page.ai.model.searchPlaceholder')"
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
          <ElTableColumn :label="$t('page.ai.model.name')" min-width="230">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <div class="ai-identity-cell">
                <span class="ai-identity-icon"><icon-material-symbols-neurology-outline-rounded /></span>
                <span class="ai-identity-copy">
                  <span class="ai-name-line">
                    <strong>{{ row.name }}</strong>
                    <span v-if="row.isDefault" class="table-chip">{{ $t('page.ai.model.default') }}</span>
                  </span>
                  <small>{{ row.modelId }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.model.provider')" min-width="170">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="ai-secondary">{{ row.providerName || '-' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.model.taskTypes')" min-width="280">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <div class="table-chip-list">
                <span v-for="task in row.taskTypes" :key="task" class="table-chip">{{ getTaskTypeLabel(task) }}</span>
                <span v-if="!row.taskTypes.length" class="table-empty">-</span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.model.reasoningEffort')" width="120" align="center">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="ai-secondary">{{ getReasoningEffortLabel(row.reasoningEffort) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.model.maxOutputTokens')" min-width="150" align="right">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="ai-number">{{ row.maxOutputTokens.toLocaleString() }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.ai.model.contextWindowTokens')" min-width="165" align="right">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="ai-number">{{ row.contextWindowTokens.toLocaleString() }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.manage.user.userStatus')" width="100" align="center">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="table-status" :class="[row.enabled ? 'is-enabled' : 'is-disabled']">
                <span />
                {{ $t(row.enabled ? 'page.manage.common.status.enable' : 'page.manage.common.status.disable') }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('page.manage.common.updatedAt')" min-width="160">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn :label="$t('common.operate')" width="150" align="right" fixed="right">
            <template #default="{ row }: { row: Api.AIManage.Model }">
              <div class="table-row-actions">
                <ElButton
                  text
                  circle
                  class="table-row-action"
                  :loading="testingId === row.id"
                  :disabled="!row.enabled"
                  :aria-label="$t('page.ai.model.testConnection')"
                  :title="$t('page.ai.model.testConnection')"
                  @click="handleTest(row)"
                >
                  <icon-carbon-play />
                </ElButton>
                <ElButton
                  text
                  circle
                  class="table-row-action"
                  :aria-label="$t('common.edit')"
                  :title="$t('common.edit')"
                  @click="handleEdit(row)"
                >
                  <icon-material-symbols-edit-outline-rounded />
                </ElButton>
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

      <ModelOperateDrawer
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
