<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchGetTools } from '@/service/api';

defineOptions({ name: 'ToolsCenter' });
const router = useRouter();
const loading = ref(false);
const tools = ref<Api.ToolManage.ToolDefinition[]>([]);
const enabledCount = computed(() => tools.value.filter(item => item.enabled).length);

const entrances = [
  {
    name: 'tools_connections',
    title: '外部连接',
    text: '集中保存 MySQL、Nacos 和缺陷平台连接，凭据加密存储。',
    icon: 'mdi:connection'
  },
  {
    name: 'tools_file-templates',
    title: '文件模板',
    text: '配置 CSV、Excel、TXT、JSON、XML 字段、校验和汇总规则。',
    icon: 'mdi:file-table-outline'
  },
  {
    name: 'tools_tasks',
    title: '任务与审批',
    text: '先生成可信预览，再审批、执行、下载产物或回滚。',
    icon: 'mdi:clipboard-text-clock-outline'
  }
];

async function loadData() {
  loading.value = true;
  const { data, error } = await fetchGetTools();
  loading.value = false;
  if (!error) tools.value = data;
}
onMounted(loadData);
</script>

<template>
  <div class="tool-page">
    <ElCard v-loading="loading" class="tool-card">
      <template #header>
        <div class="tool-heading">
          <div>
            <h2>测试工具中心</h2>
            <p>固定执行器、外部连接和人工审批共同限制 Agent 的可执行边界</p>
          </div>
          <ElTag type="success">{{ enabledCount }} 个工具已启用</ElTag>
        </div>
      </template>
      <ElAlert title="安全执行流程" type="info" :closable="false" show-icon>
        <template #default>
          创建任务 → 服务器读取真实状态并生成预览 → 中高风险任务人工审批 → 执行前再次核对预览 →
          保存日志、产物和回滚信息。
        </template>
      </ElAlert>
      <div class="entrance-grid">
        <button v-for="item in entrances" :key="item.name" type="button" @click="router.push({ name: item.name })">
          <span><SvgIcon :icon="item.icon" /></span>
          <strong>{{ item.title }}</strong>
          <small>{{ item.text }}</small>
        </button>
      </div>
      <h3 class="catalog-title">已注册工具</h3>
      <div class="catalog-grid">
        <article v-for="item in tools" :key="item.id">
          <div>
            <strong>{{ item.name }}</strong>
            <ElTag
              size="small"
              :type="item.riskLevel === 'HIGH' ? 'danger' : item.riskLevel === 'MEDIUM' ? 'warning' : 'success'"
            >
              {{ item.riskLevel }}
            </ElTag>
          </div>
          <p>{{ item.description }}</p>
          <code>{{ item.code }}</code>
        </article>
      </div>
    </ElCard>
  </div>
</template>

<style src="../shared.scss" scoped lang="scss"></style>

<style scoped lang="scss">
.entrance-grid,
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 14px;
  margin-top: 18px;
}
.entrance-grid button {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 3px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  background: var(--el-bg-color);
  padding: 16px;
  text-align: left;
  cursor: pointer;
  transition: 0.18s ease;
}
.entrance-grid button:hover {
  border-color: var(--el-color-primary-light-5);
  transform: translateY(-2px);
  box-shadow: var(--el-box-shadow-light);
}
.entrance-grid span {
  display: inline-flex;
  grid-row: 1 / 3;
  width: 42px;
  height: 42px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 21px;
}
.entrance-grid strong {
  font-size: 14px;
}
.entrance-grid small {
  color: var(--el-text-color-secondary);
  line-height: 1.55;
}
.catalog-title {
  margin: 28px 0 0;
  font-size: 14px;
}
.catalog-grid article {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 9px;
  padding: 14px;
}
.catalog-grid article > div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.catalog-grid p {
  min-height: 38px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.55;
}
.catalog-grid code {
  color: var(--el-color-primary);
  font-size: 11px;
}
</style>
