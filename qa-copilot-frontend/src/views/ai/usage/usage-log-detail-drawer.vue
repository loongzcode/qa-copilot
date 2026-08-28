<script setup lang="ts">
import dayjs from 'dayjs';

defineOptions({ name: 'AIUsageLogDetailDrawer' });

defineProps<{
  loading: boolean;
  data: Api.AIManage.UsageLogDetail | null;
}>();

const visible = defineModel<boolean>('visible', { default: false });

function taskTypeLabel(taskType: string) {
  return (
    {
      embedding: '文本向量化',
      rerank: '检索重排序',
      knowledge_qa: '知识问答',
      query_rewrite: '问题改写',
      connection_test: '模型连接测试',
      memory_summary: '会话记忆摘要',
      requirement_analysis: '需求解析',
      supervisor_planning: 'Supervisor 目标规划',
      test_case_generation: '用例生成'
    }[taskType] ?? taskType
  );
}

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN');
}
</script>

<template>
  <ElDrawer v-model="visible" size="min(620px, 94vw)" destroy-on-close>
    <template #header>
      <div class="usage-detail-heading">
        <span><SvgIcon icon="mdi:file-search-outline" /></span>
        <div>
          <strong>调用日志详情</strong>
          <small v-if="data">日志 #{{ data.id }} · {{ taskTypeLabel(data.taskType) }}</small>
        </div>
      </div>
    </template>

    <div v-loading="loading" class="usage-detail-body">
      <template v-if="data">
        <ElAlert v-if="data.status === 'failed'" title="本次 AI 调用失败" type="error" :closable="false" show-icon>
          <template #default>
            <span class="usage-error-message">{{ data.errorMessage || '未记录失败原因' }}</span>
          </template>
        </ElAlert>

        <section class="usage-detail-section">
          <h3>调用身份</h3>
          <ElDescriptions :column="1" border>
            <ElDescriptionsItem label="请求 ID">
              <code>{{ data.requestId || '-' }}</code>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="任务 ID">
              <code>{{ data.taskId || '-' }}</code>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="调用用户">
              {{ data.userName || '系统后台任务' }}
              <small v-if="data.userId">（ID: {{ data.userId }}）</small>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="所属项目">
              {{ data.projectName || '系统级调用' }}
              <small v-if="data.projectId">（ID: {{ data.projectId }}）</small>
            </ElDescriptionsItem>
          </ElDescriptions>
        </section>

        <section class="usage-detail-section">
          <h3>模型与任务</h3>
          <ElDescriptions :column="1" border>
            <ElDescriptionsItem label="服务商">
              {{ data.providerName }}
              <small v-if="data.providerId">（ID: {{ data.providerId }}）</small>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="模型">{{ data.modelName }}</ElDescriptionsItem>
            <ElDescriptionsItem label="任务类型">{{ taskTypeLabel(data.taskType) }}</ElDescriptionsItem>
            <ElDescriptionsItem label="执行状态">
              <ElTag :type="data.status === 'success' ? 'success' : 'danger'" effect="light">
                {{ data.status === 'success' ? '成功' : '失败' }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="发生时间">
              {{ dayjs(data.createdAt).format('YYYY-MM-DD HH:mm:ss') }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </section>

        <section class="usage-detail-section">
          <h3>用量与性能</h3>
          <div class="usage-metric-grid">
            <div>
              <span>输入 Token</span>
              <strong>{{ formatNumber(data.inputTokens) }}</strong>
            </div>
            <div>
              <span>输出 Token</span>
              <strong>{{ formatNumber(data.outputTokens) }}</strong>
            </div>
            <div>
              <span>总 Token</span>
              <strong>{{ formatNumber(data.totalTokens) }}</strong>
            </div>
            <div>
              <span>调用耗时</span>
              <strong>{{ formatNumber(data.latencyMs) }} ms</strong>
            </div>
            <div>
              <span>检索命中</span>
              <strong>{{ formatNumber(data.retrievalHitCount) }}</strong>
            </div>
          </div>
        </section>
      </template>
      <ElEmpty v-else-if="!loading" description="暂无调用详情" />
    </div>
  </ElDrawer>
</template>

<style scoped lang="scss">
.usage-detail-heading {
  display: flex;
  align-items: center;
  gap: 10px;

  > span {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 9px;
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    font-size: 18px;
  }

  > div {
    display: flex;
    flex-direction: column;
  }

  strong {
    color: var(--el-text-color-primary);
    font-size: 15px;
  }

  small {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.usage-detail-body {
  min-height: 260px;
}

.usage-detail-section + .usage-detail-section {
  margin-top: 22px;
}

.usage-detail-section h3 {
  margin: 0 0 10px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 650;
}

.usage-detail-section code {
  color: var(--el-text-color-regular);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.usage-detail-section small {
  color: var(--el-text-color-secondary);
}

.usage-error-message {
  white-space: pre-wrap;
  word-break: break-word;
}

.usage-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;

  > div {
    display: flex;
    min-height: 76px;
    flex-direction: column;
    justify-content: center;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    background: var(--el-fill-color-extra-light);
    padding: 12px 14px;
  }

  span {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  strong {
    margin-top: 5px;
    color: var(--el-text-color-primary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 18px;
    font-variant-numeric: tabular-nums;
  }
}

@media (max-width: 520px) {
  .usage-metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
