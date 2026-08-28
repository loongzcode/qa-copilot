<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import dayjs from 'dayjs';
import { fetchDeletePromptTemplate, fetchGetPromptTemplateList } from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import PromptOperateDrawer from './prompt-operate-drawer.vue';

defineOptions({ name: 'AIPromptManage' });

type StatusFilter = 'all' | 'enabled' | 'disabled';

const BUILT_IN_PROMPT_CODES = new Set(['rag_answer', 'query_rewrite', 'document_summary']);

const authStore = useAuthStore();
const loading = ref(false);
const records = ref<Api.AIManage.PromptTemplateSummary[]>([]);
const total = ref(0);
const statusFilter = ref<StatusFilter>('all');
const drawerVisible = ref(false);
const operateType = ref<UI.TableOperateType>('add');
const editingData = ref<Api.AIManage.PromptTemplateSummary | null>(null);

const searchParams = reactive<Api.AIManage.PromptTemplateSearchParams>({
  current: 1,
  size: 10,
  keyword: ''
});

const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('ai:prompt:manage');
});

function isBuiltIn(code: string) {
  return BUILT_IN_PROMPT_CODES.has(code);
}

async function getData() {
  loading.value = true;
  const { data, error } = await fetchGetPromptTemplateList({
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;

  if (error) return;

  records.value = data.records;
  total.value = data.total;
}

function handleAdd() {
  operateType.value = 'add';
  editingData.value = null;
  drawerVisible.value = true;
}

function handleEdit(row: Api.AIManage.PromptTemplateSummary) {
  operateType.value = 'edit';
  editingData.value = row;
  drawerVisible.value = true;
}

async function handleSearch() {
  searchParams.current = 1;
  await getData();
}

async function handleStatusChange() {
  searchParams.enabled = statusFilter.value === 'all' ? undefined : statusFilter.value === 'enabled';
  searchParams.current = 1;
  await getData();
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

async function handleDelete(row: Api.AIManage.PromptTemplateSummary) {
  const { error } = await fetchDeletePromptTemplate(row.id);
  if (error) return;

  window.$message?.success(`Prompt 模板“${row.name}”已删除`);

  // 删除当前页最后一条记录后回到上一页，避免停留在空页。
  if (records.value.length === 1 && searchParams.current > 1) {
    searchParams.current -= 1;
  }
  await getData();
}

async function handleSubmitted() {
  if (operateType.value === 'add') searchParams.current = 1;
  await getData();
}

getData();
</script>

<template>
  <div class="manage-table-page ai-list-page prompt-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>Prompt 模板</h2>
            <p>集中维护 AI 工作流使用的系统提示词、用户提示词及运行状态</p>
          </div>
          <div class="manage-table-header__actions">
            <ElTooltip content="刷新" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <icon-mdi-refresh :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <ElButton v-if="canManage" type="primary" @click="handleAdd">
              <template #icon><icon-ic-round-plus /></template>
              新增 Prompt
            </ElButton>
          </div>
        </div>
      </template>

      <div class="manage-table-toolbar">
        <ElInput
          v-model="searchParams.keyword"
          clearable
          class="manage-table-search"
          placeholder="搜索模板名称、编码或说明"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElButton type="primary" plain @click="handleSearch">查询</ElButton>
        <ElSelect v-model="statusFilter" class="ai-status-filter" @change="handleStatusChange">
          <ElOption label="全部状态" value="all" />
          <ElOption label="启用" value="enabled" />
          <ElOption label="停用" value="disabled" />
        </ElSelect>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="id">
          <ElTableColumn label="Prompt 模板" min-width="240">
            <template #default="{ row }">
              <div class="ai-identity-cell">
                <span class="ai-identity-icon"><icon-material-symbols-edit-note-rounded /></span>
                <span class="ai-identity-copy">
                  <span class="ai-name-line">
                    <strong>{{ row.name }}</strong>
                    <span v-if="isBuiltIn(row.code)" class="table-chip">系统内置</span>
                  </span>
                  <small>{{ row.code }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="description" label="用途说明" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="ai-secondary">{{ row.description || '-' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="100" align="center">
            <template #default="{ row }">
              <span class="table-status" :class="row.enabled ? 'is-enabled' : 'is-disabled'">
                <span />
                {{ row.enabled ? '启用' : '停用' }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" min-width="160">
            <template #default="{ row }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn v-if="canManage" label="操作" width="104" align="right" fixed="right">
            <template #default="{ row }">
              <div class="table-row-actions">
                <ElTooltip content="编辑 Prompt" placement="top">
                  <ElButton text circle class="table-row-action" @click="handleEdit(row)">
                    <icon-material-symbols-edit-outline-rounded />
                  </ElButton>
                </ElTooltip>

                <ElTooltip v-if="isBuiltIn(row.code)" content="系统内置模板不可删除，可在编辑中停用" placement="top">
                  <span class="prompt-disabled-action">
                    <ElButton text circle disabled class="table-row-action is-danger">
                      <icon-ic-round-delete />
                    </ElButton>
                  </span>
                </ElTooltip>
                <ElPopconfirm
                  v-else
                  width="260"
                  :title="`确认删除 Prompt 模板“${row.name}”吗？`"
                  confirm-button-text="确认删除"
                  cancel-button-text="取消"
                  @confirm="handleDelete(row)"
                >
                  <template #reference>
                    <ElButton text circle class="table-row-action is-danger" title="删除 Prompt">
                      <icon-ic-round-delete />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="暂无 Prompt 模板" :image-size="72" /></template>
        </ElTable>
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

    <PromptOperateDrawer
      v-model:visible="drawerVisible"
      :operate-type="operateType"
      :row-data="editingData"
      @submitted="handleSubmitted"
    />
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.prompt-disabled-action {
  display: inline-flex;
}

@media (max-width: 700px) {
  .manage-table-toolbar .el-button,
  .ai-status-filter {
    width: 100%;
  }
}
</style>
