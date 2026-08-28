<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue';
import { useDebounceFn, useMediaQuery } from '@vueuse/core';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCreateKnowledgeBase,
  fetchDeleteKnowledgeBase,
  fetchGetKnowledgeBaseList,
  fetchGetKnowledgeModelOptions,
  fetchGetProjectList,
  fetchUpdateKnowledgeBase
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import { visibilityOptions } from '../shared';

defineOptions({ name: 'KnowledgeBases' });

type KnowledgeBaseForm = {
  name: string;
  description: string;
  visibility: Api.KnowledgeManage.Visibility;
  embeddingModelId: number | null;
  rerankModelId: number | null;
  enabled: boolean;
};

const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const projectLoading = ref(false);
const submitting = ref(false);
const modelOptionsLoading = ref(false);
const togglingId = ref<number | null>(null);
const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const records = ref<Api.KnowledgeManage.KnowledgeBase[]>([]);
const total = ref(0);
const embeddingModelOptions = ref<Api.KnowledgeManage.ModelOption[]>([]);
const rerankModelOptions = ref<Api.KnowledgeManage.ModelOption[]>([]);
const formRef = ref<FormInstance>();
const searchParams = reactive<Api.KnowledgeManage.KnowledgeBaseSearchParams>({
  current: 1,
  size: 10,
  keyword: ''
});
const form = reactive<KnowledgeBaseForm>({
  name: '',
  description: '',
  visibility: 'PROJECT',
  embeddingModelId: null,
  rerankModelId: null,
  enabled: true
});

const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const activeProject = computed(() => projects.value.find(item => item.id === activeProjectId.value));
const isArchivedProject = computed(() => activeProject.value?.status === 'ARCHIVED');
const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('knowledge:base:manage');
});

const rules: FormRules<KnowledgeBaseForm> = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  visibility: [{ required: true, message: '请选择可见范围', trigger: 'change' }],
  embeddingModelId: [{ required: true, message: '请选择 Embedding 模型', trigger: 'change' }]
};

function visibilityLabel(value: Api.KnowledgeManage.Visibility) {
  return visibilityOptions.find(item => item.value === value)?.label ?? value;
}

async function getProjects() {
  projectLoading.value = true;
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  projectLoading.value = false;
  if (error) return;

  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getData() {
  if (!activeProjectId.value) {
    records.value = [];
    total.value = 0;
    return;
  }

  loading.value = true;
  const { data, error } = await fetchGetKnowledgeBaseList(activeProjectId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;
  if (error) return;

  records.value = data.records;
  total.value = data.total;
}

async function getModelOptions() {
  modelOptionsLoading.value = true;
  const [embeddingResult, rerankResult] = await Promise.all([
    fetchGetKnowledgeModelOptions('embedding'),
    fetchGetKnowledgeModelOptions('rerank')
  ]);
  modelOptionsLoading.value = false;

  if (!embeddingResult.error) embeddingModelOptions.value = embeddingResult.data;
  if (!rerankResult.error) rerankModelOptions.value = rerankResult.data;
}

async function handleProjectChange() {
  searchParams.current = 1;
  searchParams.keyword = '';
  await getData();
}

const handleSearch = useDebounceFn(() => {
  searchParams.current = 1;
  void getData();
}, 300);

function addCurrentModelOptions(row: Api.KnowledgeManage.KnowledgeBase) {
  if (!embeddingModelOptions.value.some(item => item.id === row.embeddingModelId)) {
    embeddingModelOptions.value.unshift({
      id: row.embeddingModelId,
      name: row.embeddingModelName,
      modelId: '',
      providerName: '当前配置（可能已停用）'
    });
  }
  if (row.rerankModelId && !rerankModelOptions.value.some(item => item.id === row.rerankModelId)) {
    rerankModelOptions.value.unshift({
      id: row.rerankModelId,
      name: row.rerankModelName || '当前 Rerank 模型',
      modelId: '',
      providerName: '当前配置（可能已停用）'
    });
  }
}

async function openDialog(row?: Api.KnowledgeManage.KnowledgeBase) {
  if (!activeProjectId.value) {
    window.$message?.warning('请先选择项目');
    return;
  }
  if (isArchivedProject.value) {
    window.$message?.warning('已归档项目不能管理知识库');
    return;
  }

  await getModelOptions();
  if (row) addCurrentModelOptions(row);

  editingId.value = row?.id ?? null;
  Object.assign(
    form,
    row
      ? {
          name: row.name,
          description: row.description,
          visibility: row.visibility,
          embeddingModelId: row.embeddingModelId,
          rerankModelId: row.rerankModelId,
          enabled: row.enabled
        }
      : {
          name: '',
          description: '',
          visibility: 'PROJECT',
          embeddingModelId: embeddingModelOptions.value[0]?.id ?? null,
          rerankModelId: null,
          enabled: true
        }
  );
  dialogVisible.value = true;
  await nextTick();
  formRef.value?.clearValidate();

  if (!row && !embeddingModelOptions.value.length) {
    window.$message?.warning('尚未配置可用的 Embedding 模型，请先联系系统管理员');
  }
}

async function submitForm() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !activeProjectId.value || !form.embeddingModelId) return;

  const baseData: Api.KnowledgeManage.KnowledgeBaseCreateParams = {
    name: form.name.trim(),
    description: form.description.trim(),
    visibility: form.visibility,
    embeddingModelId: form.embeddingModelId,
    rerankModelId: form.rerankModelId,
    enabled: form.enabled
  };

  submitting.value = true;
  let error: unknown = null;
  if (editingId.value) {
    const current = records.value.find(item => item.id === editingId.value);
    const updateData: Api.KnowledgeManage.KnowledgeBaseUpdateParams = { ...baseData };
    if (current?.embeddingModelId === form.embeddingModelId) delete updateData.embeddingModelId;
    if (current?.rerankModelId === form.rerankModelId) delete updateData.rerankModelId;
    ({ error } = await fetchUpdateKnowledgeBase(activeProjectId.value, editingId.value, updateData));
  } else {
    ({ error } = await fetchCreateKnowledgeBase(activeProjectId.value, baseData));
  }
  submitting.value = false;
  if (error) return;

  dialogVisible.value = false;
  window.$message?.success(editingId.value ? '知识库已更新' : '知识库已创建');
  await getData();
}

async function toggleKnowledgeBase(row: Api.KnowledgeManage.KnowledgeBase, enabled: boolean) {
  if (!activeProjectId.value) return;

  togglingId.value = row.id;
  const { data, error } = await fetchUpdateKnowledgeBase(activeProjectId.value, row.id, { enabled });
  togglingId.value = null;
  if (error) {
    row.enabled = !enabled;
    return;
  }
  Object.assign(row, data);
  window.$message?.success(enabled ? '知识库已启用' : '知识库已停用');
}

async function deleteKnowledgeBase(row: Api.KnowledgeManage.KnowledgeBase) {
  if (!activeProjectId.value) return;

  const { error } = await fetchDeleteKnowledgeBase(activeProjectId.value, row.id);
  if (error) return;

  if (records.value.length === 1 && searchParams.current > 1) searchParams.current -= 1;
  window.$message?.success('知识库已删除');
  await getData();
}

function handleCurrentChange() {
  void getData();
}

function handleSizeChange() {
  searchParams.current = 1;
  void getData();
}

async function init() {
  await getProjects();
  await getData();
}

void init();
</script>

<template>
  <div class="project-page manage-table-page">
    <ElCard class="project-card manage-table-card">
      <template #header>
        <div class="project-page-header">
          <div class="project-page-title">
            <h2>知识库管理</h2>
            <p>按项目沉淀测试资料，并为检索配置向量化和重排模型</p>
          </div>
          <div class="project-page-actions">
            <ElButton
              v-if="canManage"
              type="primary"
              :disabled="!activeProjectId || isArchivedProject"
              @click="openDialog()"
            >
              <template #icon><icon-ic-round-plus /></template>
              新建知识库
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
          v-model="searchParams.keyword"
          clearable
          class="project-search"
          placeholder="搜索知识库名称或说明"
          @input="handleSearch()"
          @clear="handleSearch()"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <span class="knowledge-page-note">
          <SvgIcon icon="mdi:shield-lock-outline" />
          知识数据按项目隔离
        </span>
      </div>

      <div v-if="!isMobile" class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="id">
          <ElTableColumn label="知识库" min-width="220">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeBase }">
              <div class="project-name-cell">
                <span class="project-name-icon"><SvgIcon icon="mdi:database-outline" /></span>
                <span class="project-name-copy">
                  <strong>{{ row.name }}</strong>
                  <small>{{ visibilityLabel(row.visibility) }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="description" label="说明" min-width="240" show-overflow-tooltip />
          <ElTableColumn label="检索模型" min-width="210">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeBase }">
              <div class="model-cell">
                <span>{{ row.embeddingModelName }}</span>
                <small>{{ row.rerankModelName || '未配置 Rerank' }}</small>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="文档 / 切片" width="112" align="center">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeBase }">
              <span class="knowledge-stat">{{ row.documentCount }} / {{ row.chunkCount }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="启用" width="78" align="center">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeBase }">
              <ElSwitch
                v-model="row.enabled"
                :loading="togglingId === row.id"
                :disabled="!canManage || isArchivedProject"
                @change="value => toggleKnowledgeBase(row, Boolean(value))"
              />
            </template>
          </ElTableColumn>
          <ElTableColumn prop="updatedAt" label="更新时间" min-width="150">
            <template #default="{ row }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn v-if="canManage" label="操作" width="90" align="right" fixed="right">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeBase }">
              <div class="table-row-actions">
                <ElButton text circle class="table-row-action" :disabled="isArchivedProject" @click="openDialog(row)">
                  <icon-material-symbols-edit-outline-rounded />
                </ElButton>
                <ElPopconfirm
                  title="删除知识库后文档和索引将不可恢复，确认继续？"
                  width="280"
                  @confirm="deleteKnowledgeBase(row)"
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
          <template #empty><ElEmpty description="当前项目暂无知识库" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else class="knowledge-mobile-list">
        <div v-for="row in records" :key="row.id" class="knowledge-mobile-card">
          <div class="knowledge-mobile-head">
            <div class="project-name-cell">
              <span class="project-name-icon"><SvgIcon icon="mdi:database-outline" /></span>
              <span class="project-name-copy">
                <strong>{{ row.name }}</strong>
                <small>{{ visibilityLabel(row.visibility) }}</small>
              </span>
            </div>
            <ElSwitch
              v-model="row.enabled"
              :loading="togglingId === row.id"
              :disabled="!canManage || isArchivedProject"
              @change="value => toggleKnowledgeBase(row, Boolean(value))"
            />
          </div>
          <p class="knowledge-mobile-description">{{ row.description || '暂无说明' }}</p>
          <div class="model-tags">
            <ElTag size="small" effect="plain">{{ row.embeddingModelName }}</ElTag>
            <ElTag size="small" effect="plain" type="info">{{ row.rerankModelName || '未配置 Rerank' }}</ElTag>
          </div>
          <div class="knowledge-mobile-foot">
            <span>{{ row.documentCount }} 个文档 · {{ row.chunkCount }} 个切片</span>
            <div v-if="canManage" class="table-row-actions">
              <ElButton text size="small" :disabled="isArchivedProject" @click="openDialog(row)">编辑</ElButton>
              <ElPopconfirm title="确认删除该知识库？" @confirm="deleteKnowledgeBase(row)">
                <template #reference>
                  <ElButton text size="small" type="danger" :disabled="isArchivedProject">删除</ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </div>
        </div>
        <ElEmpty v-if="!records.length" description="当前项目暂无知识库" :image-size="72" />
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

    <ElDrawer
      v-model="dialogVisible"
      :title="editingId ? '编辑知识库' : '新建知识库'"
      size="min(560px, 94vw)"
      destroy-on-close
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="知识库名称" prop="name">
          <ElInput v-model="form.name" maxlength="120" placeholder="例如：支付项目测试知识库" />
        </ElFormItem>
        <ElFormItem label="知识库说明" prop="description">
          <ElInput v-model="form.description" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </ElFormItem>
        <ElFormItem label="可见范围" prop="visibility">
          <ElSelect v-model="form.visibility" class="w-full">
            <ElOption v-for="item in visibilityOptions" :key="item.value" :label="item.label" :value="item.value" />
          </ElSelect>
        </ElFormItem>
        <div class="model-form-grid">
          <ElFormItem label="Embedding 模型" prop="embeddingModelId">
            <ElSelect
              v-model="form.embeddingModelId"
              class="w-full"
              :loading="modelOptionsLoading"
              placeholder="请选择 Embedding 模型"
            >
              <ElOption
                v-for="item in embeddingModelOptions"
                :key="item.id"
                :label="`${item.name} · ${item.providerName}`"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="Rerank 模型" prop="rerankModelId">
            <ElSelect
              v-model="form.rerankModelId"
              class="w-full"
              :loading="modelOptionsLoading"
              placeholder="不配置则跳过重排"
              clearable
            >
              <ElOption
                v-for="item in rerankModelOptions"
                :key="item.id"
                :label="`${item.name} · ${item.providerName}`"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
        </div>
        <ElFormItem label="启用状态"><ElSwitch v-model="form.enabled" active-text="允许上传、索引和问答" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">保存</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../../project/shared.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.model-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  font-size: 12px;
}
.model-cell span,
.model-cell small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-cell small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
}
.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.model-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 620px) {
  .model-form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .knowledge-page-note {
    display: none;
  }
}
</style>
