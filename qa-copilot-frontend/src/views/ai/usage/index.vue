<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import dayjs from 'dayjs';
import {
  fetchGetAIModelList,
  fetchGetAIProviderList,
  fetchGetAIUsageLogDetail,
  fetchGetAIUsageLogList,
  fetchGetAIUsageLogStatistics
} from '@/service/api';
import UsageLogDetailDrawer from './usage-log-detail-drawer.vue';

defineOptions({ name: 'AIUsageManage' });

type TimeRange = [Date, Date] | null;

const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const detailLoading = ref(false);
const detailVisible = ref(false);
const records = ref<Api.AIManage.UsageLog[]>([]);
const total = ref(0);
const providers = ref<Api.AIManage.Provider[]>([]);
const models = ref<Api.AIManage.Model[]>([]);
const detail = ref<Api.AIManage.UsageLogDetail | null>(null);
const timeRange = ref<TimeRange>(null);
const statistics = ref<Api.AIManage.UsageLogStatistics>({
  totalCalls: 0,
  successCalls: 0,
  failedCalls: 0,
  successRate: 0,
  inputTokens: 0,
  outputTokens: 0,
  totalTokens: 0,
  averageLatencyMs: 0,
  maxLatencyMs: 0,
  p95LatencyMs: 0
});

const searchParams = reactive<Api.AIManage.UsageLogSearchParams>({
  current: 1,
  size: 10,
  providerId: undefined,
  modelId: undefined,
  taskType: undefined,
  status: undefined,
  requestId: undefined,
  taskId: undefined
});

const taskTypeOptions = [
  { value: 'embedding', label: '文本向量化' },
  { value: 'rerank', label: '检索重排序' },
  { value: 'knowledge_qa', label: '知识问答' },
  { value: 'query_rewrite', label: '问题改写' },
  { value: 'connection_test', label: '模型连接测试' },
  { value: 'memory_summary', label: '会话记忆摘要' },
  { value: 'requirement_analysis', label: '需求解析' },
  { value: 'supervisor_planning', label: 'Supervisor 目标规划' },
  { value: 'test_case_generation', label: '用例生成' }
];

const modelOptions = computed(() => {
  if (!searchParams.providerId) return models.value;
  return models.value.filter(item => item.providerId === searchParams.providerId);
});

function taskTypeLabel(taskType: string) {
  return taskTypeOptions.find(item => item.value === taskType)?.label ?? taskType;
}

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN');
}

function formatLatency(value: number) {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function buildFilterParams(): Api.AIManage.UsageLogFilterParams {
  return {
    providerId: searchParams.providerId,
    modelId: searchParams.modelId,
    taskType: searchParams.taskType,
    status: searchParams.status,
    requestId: searchParams.requestId?.trim() || undefined,
    taskId: searchParams.taskId?.trim() || undefined,
    startTime: timeRange.value ? dayjs(timeRange.value[0]).toISOString() : undefined,
    endTime: timeRange.value ? dayjs(timeRange.value[1]).toISOString() : undefined
  };
}

async function getOptions() {
  const [providerResult, modelResult] = await Promise.all([fetchGetAIProviderList(), fetchGetAIModelList()]);

  if (!providerResult.error) providers.value = providerResult.data;
  if (!modelResult.error) models.value = modelResult.data;
}

async function getData() {
  loading.value = true;
  const filters = buildFilterParams();
  const [listResult, statisticsResult] = await Promise.all([
    fetchGetAIUsageLogList({
      ...filters,
      current: searchParams.current,
      size: searchParams.size
    }),
    fetchGetAIUsageLogStatistics(filters)
  ]);
  loading.value = false;

  if (!listResult.error) {
    records.value = listResult.data.records;
    total.value = listResult.data.total;
  }
  if (!statisticsResult.error) statistics.value = statisticsResult.data;
}

async function handleSearch() {
  searchParams.current = 1;
  await getData();
}

async function handleReset() {
  Object.assign(searchParams, {
    current: 1,
    providerId: undefined,
    modelId: undefined,
    taskType: undefined,
    status: undefined,
    requestId: undefined,
    taskId: undefined
  });
  timeRange.value = null;
  await getData();
}

async function handleProviderChange() {
  if (searchParams.modelId && !modelOptions.value.some(item => item.id === searchParams.modelId)) {
    searchParams.modelId = undefined;
  }
}

async function handleCurrentChange(current: number) {
  searchParams.current = current;
  await getData();
}

async function handleSizeChange(size: number) {
  searchParams.current = 1;
  searchParams.size = size;
  await getData();
}

async function showDetail(row: Api.AIManage.UsageLog) {
  detail.value = null;
  detailVisible.value = true;
  detailLoading.value = true;
  const { data, error } = await fetchGetAIUsageLogDetail(row.id);
  detailLoading.value = false;
  if (error) {
    detailVisible.value = false;
    return;
  }
  detail.value = data;
}

void Promise.all([getOptions(), getData()]);
</script>

<template>
  <div class="manage-table-page usage-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>AI 调用日志</h2>
            <p>查看模型调用状态、Token 消耗、响应耗时和脱敏后的失败原因</p>
          </div>
          <div class="manage-table-header__actions">
            <ElTooltip content="刷新当前数据" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <SvgIcon icon="mdi:refresh" :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
          </div>
        </div>
      </template>

      <section class="usage-stat-grid">
        <div class="usage-stat-card">
          <span>
            <SvgIcon icon="mdi:chart-box-outline" />
            调用总数
          </span>
          <strong>{{ formatNumber(statistics.totalCalls) }}</strong>
          <small>当前筛选范围</small>
        </div>
        <div class="usage-stat-card">
          <span>
            <SvgIcon icon="mdi:check-decagram-outline" />
            成功率
          </span>
          <strong>{{ statistics.successRate.toFixed(2) }}%</strong>
          <small>
            {{ formatNumber(statistics.successCalls) }} 成功 · {{ formatNumber(statistics.failedCalls) }} 失败
          </small>
        </div>
        <div class="usage-stat-card">
          <span>
            <SvgIcon icon="mdi:counter" />
            总 Token
          </span>
          <strong>{{ formatNumber(statistics.totalTokens) }}</strong>
          <small>
            {{ formatNumber(statistics.inputTokens) }} 输入 · {{ formatNumber(statistics.outputTokens) }} 输出
          </small>
        </div>
        <div class="usage-stat-card">
          <span>
            <SvgIcon icon="mdi:timer-outline" />
            平均耗时
          </span>
          <strong>{{ formatLatency(statistics.averageLatencyMs) }}</strong>
          <small>最大 {{ formatLatency(statistics.maxLatencyMs) }}</small>
        </div>
        <div class="usage-stat-card">
          <span>
            <SvgIcon icon="mdi:speedometer" />
            P95 耗时
          </span>
          <strong>{{ formatLatency(statistics.p95LatencyMs) }}</strong>
          <small>95% 调用不超过此耗时</small>
        </div>
      </section>

      <section class="usage-filter-panel">
        <ElSelect
          v-model="searchParams.providerId"
          clearable
          filterable
          placeholder="全部服务商"
          @change="handleProviderChange"
        >
          <ElOption v-for="item in providers" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElSelect v-model="searchParams.modelId" clearable filterable placeholder="全部模型">
          <ElOption v-for="item in modelOptions" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElSelect v-model="searchParams.taskType" clearable placeholder="全部任务类型">
          <ElOption v-for="item in taskTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect v-model="searchParams.status" clearable placeholder="全部状态">
          <ElOption label="成功" value="success" />
          <ElOption label="失败" value="failed" />
        </ElSelect>
        <ElDatePicker
          v-model="timeRange"
          type="datetimerange"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          range-separator="至"
          :clearable="true"
        />
        <ElInput v-model="searchParams.requestId" clearable placeholder="请求 ID" @keyup.enter="handleSearch" />
        <ElInput v-model="searchParams.taskId" clearable placeholder="任务 ID" @keyup.enter="handleSearch" />
        <div class="usage-filter-actions">
          <ElButton type="primary" @click="handleSearch">查询</ElButton>
          <ElButton @click="handleReset">重置</ElButton>
        </div>
      </section>

      <div v-if="!isMobile" class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="id">
          <ElTableColumn label="调用时间" width="168">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <span class="table-date">{{ dayjs(row.createdAt).format('YYYY-MM-DD HH:mm:ss') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="任务类型" min-width="150">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <span class="usage-task-chip">{{ taskTypeLabel(row.taskType) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="模型 / 服务商" min-width="220">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <div class="usage-model-cell">
                <strong>{{ row.modelName }}</strong>
                <small>{{ row.providerName }}</small>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="用户 / 项目" min-width="190">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <div class="usage-model-cell">
                <strong>{{ row.userName || '系统后台任务' }}</strong>
                <small>{{ row.projectName || '系统级调用' }}</small>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="90" align="center">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <span class="usage-status" :class="[row.status === 'success' ? 'is-success' : 'is-failed']">
                <i />
                {{ row.status === 'success' ? '成功' : '失败' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="Token" width="125" align="right">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <strong class="usage-number">{{ formatNumber(row.totalTokens) }}</strong>
              <small class="usage-number-note">
                {{ formatNumber(row.inputTokens) }} / {{ formatNumber(row.outputTokens) }}
              </small>
            </template>
          </ElTableColumn>
          <ElTableColumn label="耗时" width="105" align="right">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <span class="usage-number">{{ formatLatency(row.latencyMs) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="78" align="center" fixed="right">
            <template #default="{ row }: { row: Api.AIManage.UsageLog }">
              <ElButton text circle class="table-row-action" title="查看详情" @click="showDetail(row)">
                <SvgIcon icon="mdi:eye-outline" />
              </ElButton>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="暂无调用日志" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else v-loading="loading" class="usage-mobile-list">
        <button v-for="row in records" :key="row.id" type="button" class="usage-mobile-card" @click="showDetail(row)">
          <span class="usage-mobile-head">
            <span>
              <strong>{{ taskTypeLabel(row.taskType) }}</strong>
              <small>{{ dayjs(row.createdAt).format('MM-DD HH:mm:ss') }}</small>
            </span>
            <span class="usage-status" :class="[row.status === 'success' ? 'is-success' : 'is-failed']">
              <i />
              {{ row.status === 'success' ? '成功' : '失败' }}
            </span>
          </span>
          <span class="usage-mobile-model">{{ row.modelName }} · {{ row.providerName }}</span>
          <span class="usage-mobile-metrics">
            <span>
              Token
              <b>{{ formatNumber(row.totalTokens) }}</b>
            </span>
            <span>
              耗时
              <b>{{ formatLatency(row.latencyMs) }}</b>
            </span>
          </span>
        </button>
        <ElEmpty v-if="!records.length && !loading" description="暂无调用日志" :image-size="72" />
      </div>

      <footer class="manage-table-footer">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, prev, pager, next, sizes"
          @current-change="handleCurrentChange"
          @size-change="handleSizeChange"
        />
      </footer>
    </ElCard>

    <UsageLogDetailDrawer v-model:visible="detailVisible" :loading="detailLoading" :data="detail" />
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style scoped lang="scss">
.usage-stat-grid {
  display: grid;
  flex: none;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 12px 16px;
}

.usage-stat-card {
  display: flex;
  min-width: 0;
  min-height: 96px;
  flex-direction: column;
  justify-content: center;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
  padding: 12px 14px;

  > span {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    overflow: hidden;
    margin-top: 7px;
    color: var(--el-text-color-primary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 21px;
    font-variant-numeric: tabular-nums;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    overflow: hidden;
    margin-top: 4px;
    color: var(--el-text-color-secondary);
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.usage-filter-panel {
  display: grid;
  flex: none;
  grid-template-columns: repeat(4, minmax(130px, 1fr)) minmax(320px, 1.8fr);
  gap: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 12px 16px;

  :deep(.el-date-editor) {
    width: 100%;
  }
}

.usage-filter-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.usage-task-chip {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 5px;
  background: var(--el-color-primary-light-9);
  padding: 0 8px;
  color: var(--el-color-primary);
  font-size: 11px;
}

.usage-model-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;

  strong,
  small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 12px;
    font-weight: 550;
  }

  small {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
    font-size: 11px;
  }
}

.usage-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--el-text-color-placeholder);
  }

  &.is-success i {
    background: var(--el-color-success);
  }

  &.is-failed {
    color: var(--el-color-danger);
  }

  &.is-failed i {
    background: var(--el-color-danger);
  }
}

.usage-number {
  display: block;
  color: var(--el-text-color-regular);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.usage-number-note {
  display: block;
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
}

.usage-mobile-list {
  min-height: 280px;
  flex: 1;
  padding: 10px;
}

.usage-mobile-card {
  display: block;
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 12px;
  color: inherit;
  text-align: left;
}

.usage-mobile-card + .usage-mobile-card {
  margin-top: 10px;
}

.usage-mobile-head,
.usage-mobile-head > span:first-child {
  display: flex;
}

.usage-mobile-head {
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;

  > span:first-child {
    flex-direction: column;
  }

  strong {
    font-size: 13px;
  }

  small {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
    font-size: 11px;
  }
}

.usage-mobile-model {
  display: block;
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.usage-mobile-metrics {
  display: flex;
  margin-top: 10px;
  gap: 18px;
  border-top: 1px solid var(--el-border-color-extra-light);
  padding-top: 9px;
  color: var(--el-text-color-secondary);
  font-size: 11px;

  b {
    margin-left: 4px;
    color: var(--el-text-color-primary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
}

@media (max-width: 1250px) {
  .usage-stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .usage-filter-panel {
    grid-template-columns: repeat(3, minmax(150px, 1fr));
  }
}

@media (max-width: 700px) {
  .usage-stat-grid,
  .usage-filter-panel {
    grid-template-columns: 1fr;
  }

  .usage-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .usage-filter-actions {
    width: 100%;

    .el-button {
      flex: 1;
    }
  }
}

@media (max-width: 430px) {
  .usage-stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
