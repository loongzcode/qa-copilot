<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useDebounceFn, useIntervalFn, useMediaQuery } from '@vueuse/core';
import type { UploadUserFile } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchDeleteKnowledgeDocument,
  fetchGetKnowledgeBaseList,
  fetchGetKnowledgeDocumentList,
  fetchGetProjectList,
  fetchGetProjectModules,
  fetchIndexKnowledgeDocument,
  fetchUploadKnowledgeDocument
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import { documentTypeOptions } from '../shared';

defineOptions({ name: 'KnowledgeDocuments' });

const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const projectLoading = ref(false);
const knowledgeBaseLoading = ref(false);
const moduleLoading = ref(false);
const uploading = ref(false);
const indexingId = ref<number | null>(null);
const deletingId = ref<number | null>(null);
const pollingCount = ref(0);
const uploadVisible = ref(false);
const activeProjectId = ref<number | null>(null);
const activeKnowledgeBaseId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const knowledgeBases = ref<Api.KnowledgeManage.KnowledgeBase[]>([]);
const modules = ref<Api.ProjectManage.ProjectModule[]>([]);
const records = ref<Api.KnowledgeManage.KnowledgeDocument[]>([]);
const total = ref(0);
const status = ref<'ALL' | Api.KnowledgeManage.KnowledgeDocumentParseStatus>('ALL');
const documentType = ref<'ALL' | Api.KnowledgeManage.KnowledgeDocumentType>('ALL');
const fileList = ref<UploadUserFile[]>([]);
const searchParams = reactive<Api.KnowledgeManage.KnowledgeDocumentSearchParams>({
  current: 1,
  size: 10,
  keyword: ''
});
const uploadForm = reactive<{
  title: string;
  documentType: Api.KnowledgeManage.KnowledgeDocumentType;
  moduleId: number | null;
}>({ title: '', documentType: 'TEST_PROCESS', moduleId: null });

const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const knowledgeBaseOptions = computed(() => knowledgeBases.value.filter(item => item.enabled));
const moduleOptions = computed(() => flattenModules(modules.value));
const activeProject = computed(() => projects.value.find(item => item.id === activeProjectId.value));
const isArchivedProject = computed(() => activeProject.value?.status === 'ARCHIVED');
const canUpload = computed(() => hasPermission('knowledge:document:upload'));
const canManage = computed(() => hasPermission('knowledge:document:manage'));
const canIndex = computed(() => hasPermission('knowledge:document:index'));

function hasPermission(code: string) {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes(code);
}

function typeLabel(value: Api.KnowledgeManage.KnowledgeDocumentType) {
  return documentTypeOptions.find(item => item.value === value)?.label ?? value;
}

function statusMeta(value: Api.KnowledgeManage.KnowledgeDocumentParseStatus) {
  return {
    PENDING: { label: '待处理', type: 'info' },
    PARSING: { label: '解析中', type: 'warning' },
    INDEXING: { label: '索引中', type: 'warning' },
    READY: { label: '已完成', type: 'success' },
    FAILED: { label: '失败', type: 'danger' }
  }[value] as { label: string; type: 'info' | 'warning' | 'success' | 'danger' };
}

function isProcessing(value: Api.KnowledgeManage.KnowledgeDocumentParseStatus) {
  return value === 'PARSING' || value === 'INDEXING';
}

function fileIcon(fileName: string) {
  const extension = fileName.split('.').pop()?.toLowerCase();
  return (
    {
      pdf: 'mdi:file-pdf-box',
      docx: 'mdi:file-word-box',
      md: 'mdi:language-markdown-outline',
      txt: 'mdi:file-document-outline'
    }[extension ?? ''] ?? 'mdi:file-outline'
  );
}

function formatFileSize(size: number | null) {
  if (size === null) return '—';
  if (size < 1024) return `${size} B`;
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 ** 2).toFixed(1)} MB`;
}

function flattenModules(items: Api.ProjectManage.ProjectModule[], depth = 0): Array<{ label: string; value: number }> {
  return items.flatMap(item => [
    { label: `${'　'.repeat(depth)}${item.name}`, value: item.id },
    ...flattenModules(item.children, depth + 1)
  ]);
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

async function getKnowledgeBases() {
  if (!activeProjectId.value) {
    knowledgeBases.value = [];
    activeKnowledgeBaseId.value = null;
    return;
  }

  knowledgeBaseLoading.value = true;
  const { data, error } = await fetchGetKnowledgeBaseList(activeProjectId.value, {
    current: 1,
    size: 100,
    keyword: '',
    enabled: true
  });
  knowledgeBaseLoading.value = false;
  if (error) return;

  knowledgeBases.value = data.records;
  if (!activeKnowledgeBaseId.value || !knowledgeBases.value.some(item => item.id === activeKnowledgeBaseId.value)) {
    activeKnowledgeBaseId.value = knowledgeBaseOptions.value[0]?.id ?? null;
  }
}

async function getModules() {
  if (!activeProjectId.value) {
    modules.value = [];
    return;
  }

  moduleLoading.value = true;
  const { data, error } = await fetchGetProjectModules(activeProjectId.value, { keyword: '' });
  moduleLoading.value = false;
  if (!error) modules.value = data;
}

async function getData(silent = false) {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) {
    records.value = [];
    total.value = 0;
    return;
  }

  if (!silent) loading.value = true;
  const { data, error } = await fetchGetKnowledgeDocumentList(activeProjectId.value, activeKnowledgeBaseId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim(),
    documentType: documentType.value === 'ALL' ? undefined : documentType.value,
    parseStatus: status.value === 'ALL' ? undefined : status.value
  });
  if (!silent) loading.value = false;
  if (error) return;

  records.value = data.records;
  total.value = data.total;
}

async function handleProjectChange() {
  searchParams.current = 1;
  searchParams.keyword = '';
  documentType.value = 'ALL';
  status.value = 'ALL';
  activeKnowledgeBaseId.value = null;
  await Promise.all([getKnowledgeBases(), getModules()]);
  await getData();
}

function handleKnowledgeBaseChange() {
  searchParams.current = 1;
  void getData();
}

function handleFilterChange() {
  searchParams.current = 1;
  void getData();
}

const handleSearch = useDebounceFn(() => {
  searchParams.current = 1;
  void getData();
}, 300);

function openUpload() {
  if (!activeKnowledgeBaseId.value) {
    window.$message?.warning('请先选择知识库');
    return;
  }
  Object.assign(uploadForm, { title: '', documentType: 'TEST_PROCESS', moduleId: null });
  fileList.value = [];
  uploadVisible.value = true;
}

async function submitUpload() {
  const rawFile = fileList.value[0]?.raw;
  if (!rawFile || !activeProjectId.value || !activeKnowledgeBaseId.value) {
    window.$message?.warning('请选择需要上传的文档');
    return;
  }

  uploading.value = true;
  const { error } = await fetchUploadKnowledgeDocument(activeProjectId.value, activeKnowledgeBaseId.value, {
    file: rawFile,
    title: uploadForm.title.trim() || undefined,
    documentType: uploadForm.documentType,
    moduleId: uploadForm.moduleId ?? undefined,
    metadata: {}
  });
  uploading.value = false;
  if (error) return;

  uploadVisible.value = false;
  window.$message?.success('文档上传成功，等待后续解析和索引');
  searchParams.current = 1;
  await getData();
}

async function retryIndex(row: Api.KnowledgeManage.KnowledgeDocument) {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) return;

  indexingId.value = row.id;
  const { error } = await fetchIndexKnowledgeDocument(activeProjectId.value, activeKnowledgeBaseId.value, row.id);
  indexingId.value = null;
  if (error) return;

  window.$message?.success(row.parseStatus === 'FAILED' ? '已重新提交索引任务' : '索引任务已提交');
  await getData();
  pollingCount.value = 0;
  resumePolling();
}

async function deleteDocument(row: Api.KnowledgeManage.KnowledgeDocument) {
  if (!activeProjectId.value || !activeKnowledgeBaseId.value) return;

  deletingId.value = row.id;
  const { error } = await fetchDeleteKnowledgeDocument(activeProjectId.value, activeKnowledgeBaseId.value, row.id);
  deletingId.value = null;
  if (error) return;

  window.$message?.success('知识文档删除成功');

  // 当前页最后一条被删除后返回上一页，避免显示一个实际上已经没有数据的空页。
  if (records.value.length === 1 && searchParams.current > 1) {
    searchParams.current -= 1;
  }
  await getData();
}

function handleCurrentChange() {
  void getData();
}

function handleSizeChange() {
  searchParams.current = 1;
  void getData();
}

const { pause: pausePolling, resume: resumePolling } = useIntervalFn(
  async () => {
    pollingCount.value += 1;
    await getData(true);
    const hasRunningTask = records.value.some(item => ['PENDING', 'PARSING', 'INDEXING'].includes(item.parseStatus));
    if (!hasRunningTask || pollingCount.value >= 150) pausePolling();
  },
  2000,
  { immediate: false }
);

async function init() {
  await getProjects();
  await Promise.all([getKnowledgeBases(), getModules()]);
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
            <h2>文档管理</h2>
            <p>上传项目测试资料，跟踪解析、切片和向量索引状态</p>
          </div>
          <div class="project-page-actions">
            <ElButton
              v-if="canUpload"
              type="primary"
              :disabled="!activeKnowledgeBaseId || isArchivedProject"
              @click="openUpload"
            >
              <template #icon><icon-ic-round-upload /></template>
              上传文档
            </ElButton>
          </div>
        </div>
      </template>

      <div class="project-toolbar document-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-selector"
          placeholder="选择项目"
          :loading="projectLoading"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect
          v-model="activeKnowledgeBaseId"
          class="knowledge-base-selector"
          placeholder="选择知识库"
          :loading="knowledgeBaseLoading"
          @change="handleKnowledgeBaseChange"
        >
          <ElOption v-for="item in knowledgeBaseOptions" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElInput
          v-model="searchParams.keyword"
          clearable
          class="project-search"
          placeholder="搜索文档、文件名或模块"
          @input="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElSelect v-model="documentType" class="document-filter" @change="handleFilterChange">
          <ElOption label="全部类型" value="ALL" />
          <ElOption v-for="item in documentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElSelect v-model="status" class="document-filter" @change="handleFilterChange">
          <ElOption label="全部状态" value="ALL" />
          <ElOption label="待处理" value="PENDING" />
          <ElOption label="解析中" value="PARSING" />
          <ElOption label="索引中" value="INDEXING" />
          <ElOption label="已完成" value="READY" />
          <ElOption label="失败" value="FAILED" />
        </ElSelect>
      </div>

      <div v-if="!isMobile" class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="id">
          <ElTableColumn label="文档" min-width="240">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeDocument }">
              <div class="project-name-cell">
                <span class="document-icon"><SvgIcon :icon="fileIcon(row.originalFilename || row.title)" /></span>
                <span class="project-name-copy">
                  <strong>{{ row.title }}</strong>
                  <small>{{ row.originalFilename || '无原始文件名' }} · {{ formatFileSize(row.sizeBytes) }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="分类 / 模块" min-width="160">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeDocument }">
              <div class="document-category">
                <ElTag size="small" effect="plain">{{ typeLabel(row.documentType) }}</ElTag>
                <span>{{ row.moduleName || '未关联模块' }}</span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="版本" width="72" align="center">
            <template #default="{ row }">v{{ row.version }}</template>
          </ElTableColumn>
          <ElTableColumn label="索引状态" min-width="130">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeDocument }">
              <ElTooltip :content="row.errorMessage || ''" :disabled="!row.errorMessage">
                <ElTag size="small" :type="statusMeta(row.parseStatus).type">
                  <icon-mdi-loading v-if="isProcessing(row.parseStatus)" class="mr-4px animate-spin" />
                  {{ statusMeta(row.parseStatus).label }}
                </ElTag>
              </ElTooltip>
            </template>
          </ElTableColumn>
          <ElTableColumn label="切片" width="76" align="center">
            <template #default="{ row }">
              <span class="knowledge-stat">{{ row.chunkCount }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="updatedAt" label="更新时间" min-width="150">
            <template #default="{ row }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="112" align="right" fixed="right">
            <template #default="{ row }: { row: Api.KnowledgeManage.KnowledgeDocument }">
              <div class="table-row-actions">
                <ElTooltip v-if="canIndex" :content="row.parseStatus === 'FAILED' ? '重试索引' : '重新索引'">
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :loading="indexingId === row.id"
                    :disabled="isProcessing(row.parseStatus) || isArchivedProject"
                    @click="retryIndex(row)"
                  >
                    <icon-mdi-refresh />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm
                  v-if="canManage"
                  title="确认删除该文档及其全部索引切片？"
                  width="260"
                  @confirm="deleteDocument(row)"
                >
                  <template #reference>
                    <ElButton
                      text
                      circle
                      class="table-row-action is-danger"
                      :loading="deletingId === row.id"
                      :disabled="isArchivedProject || deletingId !== null"
                    >
                      <icon-ic-round-delete />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前知识库暂无文档" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else class="knowledge-mobile-list">
        <div v-for="row in records" :key="row.id" class="knowledge-mobile-card">
          <div class="knowledge-mobile-head">
            <div class="project-name-cell">
              <span class="document-icon"><SvgIcon :icon="fileIcon(row.originalFilename || row.title)" /></span>
              <span class="project-name-copy">
                <strong>{{ row.title }}</strong>
                <small>{{ formatFileSize(row.sizeBytes) }} · v{{ row.version }}</small>
              </span>
            </div>
            <ElTag size="small" :type="statusMeta(row.parseStatus).type">{{ statusMeta(row.parseStatus).label }}</ElTag>
          </div>
          <p class="knowledge-mobile-description">
            {{ typeLabel(row.documentType) }} · {{ row.moduleName || '未关联模块' }} · {{ row.chunkCount }} 个切片
          </p>
          <div class="knowledge-mobile-foot">
            <span>{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            <div class="table-row-actions">
              <ElButton
                v-if="canIndex"
                text
                size="small"
                :loading="indexingId === row.id"
                :disabled="isProcessing(row.parseStatus) || isArchivedProject"
                @click="retryIndex(row)"
              >
                索引
              </ElButton>
              <ElPopconfirm v-if="canManage" title="确认删除该文档？" @confirm="deleteDocument(row)">
                <template #reference>
                  <ElButton
                    text
                    size="small"
                    type="danger"
                    :loading="deletingId === row.id"
                    :disabled="isArchivedProject || deletingId !== null"
                  >
                    删除
                  </ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </div>
        </div>
        <ElEmpty v-if="!records.length" description="当前知识库暂无文档" :image-size="72" />
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

    <ElDialog v-model="uploadVisible" title="上传知识文档" width="560px" destroy-on-close>
      <ElUpload v-model:file-list="fileList" drag :auto-upload="false" :limit="1" accept=".pdf,.docx,.md,.txt">
        <icon-ep-upload-filled class="upload-icon" />
        <div class="el-upload__text">
          将文件拖到此处，或
          <em>点击选择</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF、DOCX、Markdown、TXT；单文件最大限制由后端配置。</div>
        </template>
      </ElUpload>
      <ElForm :model="uploadForm" label-position="top" class="upload-meta-form">
        <ElFormItem label="文档标题">
          <ElInput v-model="uploadForm.title" maxlength="300" placeholder="不填写时使用文件名" />
        </ElFormItem>
        <div class="upload-form-grid">
          <ElFormItem label="知识分类">
            <ElSelect v-model="uploadForm.documentType" class="w-full">
              <ElOption v-for="item in documentTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="关联模块">
            <ElSelect
              v-model="uploadForm.moduleId"
              class="w-full"
              clearable
              placeholder="不关联模块"
              :loading="moduleLoading"
            >
              <ElOption v-for="item in moduleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </ElSelect>
          </ElFormItem>
        </div>
      </ElForm>
      <template #footer>
        <ElButton :disabled="uploading" @click="uploadVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="uploading" @click="submitUpload">确认上传</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../../project/shared.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.document-toolbar {
  gap: 8px;
}
.knowledge-base-selector {
  width: 210px;
}
.document-filter {
  width: 126px;
}
.document-icon {
  display: inline-flex;
  flex: 0 0 34px;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
  background: var(--el-fill-color-light);
  color: rgb(var(--primary-color));
  font-size: 20px;
}
.document-category {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.upload-icon {
  color: var(--el-text-color-placeholder);
  font-size: 58px;
}
.upload-meta-form {
  margin-top: 18px;
}
.upload-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 1100px) {
  .document-toolbar {
    flex-wrap: wrap;
  }
}
@media (max-width: 700px) {
  .knowledge-base-selector,
  .document-filter {
    width: 100%;
  }
  .upload-form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
