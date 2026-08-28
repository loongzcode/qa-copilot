<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useDebounceFn, useMediaQuery } from '@vueuse/core';
import type { FormInstance, FormRules, UploadFile, UploadUserFile } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCreateRequirement,
  fetchDeleteRequirement,
  fetchExtractRequirement,
  fetchGetLatestRequirementExtractionTask,
  fetchGetProjectList,
  fetchGetRequirementExtractionTask,
  fetchGetRequirementFormOptions,
  fetchGetRequirementList,
  fetchUpdateRequirement,
  fetchUploadRequirementSourceDocument
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import { requirementStatusLabel, requirementStatusOptions, requirementStatusType } from '../shared';

defineOptions({ name: 'RequirementList' });

type RequirementForm = Api.RequirementManage.RequirementCreateParams;
type RequirementSourceMode = 'UPLOAD' | 'EXISTING' | 'MANUAL';

const router = useRouter();
const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const projectLoading = ref(false);
const submitting = ref(false);
const formOptionsLoading = ref(false);
const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const records = ref<Api.RequirementManage.Requirement[]>([]);
const total = ref(0);
const formRef = ref<FormInstance>();
const moduleOptions = ref<Array<{ id: number; name: string }>>([]);
const knowledgeBaseOptions = ref<Array<{ id: number; name: string }>>([]);
const documentOptions = ref<Array<{ id: number; title: string; version: number }>>([]);
/** 当前需求正文来自上传文件、已有文档还是手工填写。 */
const sourceMode = ref<RequirementSourceMode>('UPLOAD');
/** 直接上传模式下，来源文档要保存到哪个项目知识库。 */
const sourceKnowledgeBaseId = ref<number | null>(null);
const sourceFileList = ref<UploadUserFile[]>([]);
/** 上传成功但需求保存失败时保留文档 ID，用户重试不会重复上传同一文件。 */
const uploadedSourceDocumentId = ref<number | null>(null);
/** requirementId 对应的轮询定时器和准确任务 ID，避免同一需求重复启动轮询。 */
const extractionPollTimers = new Map<number, ReturnType<typeof setTimeout>>();
const extractionTaskIds = new Map<number, number>();
const resumingRequirementIds = new Set<number>();
let sourceDocumentPollTimer: ReturnType<typeof setTimeout> | null = null;

const searchParams = reactive<Api.RequirementManage.RequirementSearchParams>({
  current: 1,
  size: 10,
  keyword: '',
  status: undefined
});

const form = reactive<RequirementForm>({
  moduleId: null,
  documentId: null,
  title: '',
  version: '1.0',
  sourceUrl: null,
  summary: ''
});

const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })));
const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('requirement:manage');
});
const canExtract = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('requirement:extract');
});
const dialogTitle = computed(() => (editingId.value ? '编辑需求' : '新建需求'));

function validateManualSummary(_rule: unknown, value: unknown, callback: (error?: Error) => void) {
  if (sourceMode.value === 'MANUAL' && (typeof value !== 'string' || !value.trim())) {
    callback(new Error('手工录入时请填写需求摘要'));
    return;
  }
  callback();
}

const rules: FormRules<RequirementForm> = {
  title: [{ required: true, message: '请输入需求标题', trigger: 'blur' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'change' }],
  summary: [{ validator: validateManualSummary, trigger: 'blur' }]
};

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
  const { data, error } = await fetchGetRequirementList(activeProjectId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;
  if (error) return;

  records.value = data.records;
  total.value = data.total;
  scheduleSourceDocumentPolling();
  // 刷新列表或重新进入页面后，自动恢复仍处于拆解中的任务轮询。
  for (const record of records.value) {
    if (record.status === 'EXTRACTING') void resumeExtractionPolling(record);
  }
}

function isSourceDocumentProcessing(row: Api.RequirementManage.Requirement) {
  return (
    row.documentParseStatus === 'PENDING' ||
    row.documentParseStatus === 'PARSING' ||
    row.documentParseStatus === 'INDEXING'
  );
}

/** 上传来源文档后短暂刷新列表，解析完成便自动解除“启动拆解”按钮禁用状态。 */
function scheduleSourceDocumentPolling() {
  if (sourceDocumentPollTimer) clearTimeout(sourceDocumentPollTimer);
  sourceDocumentPollTimer = null;
  if (!records.value.some(isSourceDocumentProcessing)) return;
  sourceDocumentPollTimer = setTimeout(() => {
    void getData();
  }, 2500);
}

function sourceDocumentStatusLabel(row: Api.RequirementManage.Requirement) {
  if (row.documentParseStatus === 'FAILED') return '文档解析失败';
  if (isSourceDocumentProcessing(row)) return '文档解析中';
  return '';
}

function canStartExtraction(row: Api.RequirementManage.Requirement) {
  return !row.documentId || row.documentParseStatus === 'READY';
}

function extractionButtonTitle(row: Api.RequirementManage.Requirement) {
  if (row.documentParseStatus === 'FAILED') return '来源文档解析失败，请先到知识文档页面重试';
  if (isSourceDocumentProcessing(row)) return '来源文档解析完成后才能启动需求拆解';
  return '启动需求拆解';
}

function stopExtractionPolling(requirementId: number) {
  const timer = extractionPollTimers.get(requirementId);
  if (timer) clearTimeout(timer);
  extractionPollTimers.delete(requirementId);
  extractionTaskIds.delete(requirementId);
}

function stopAllExtractionPolling() {
  for (const requirementId of extractionPollTimers.keys()) {
    stopExtractionPolling(requirementId);
  }
  resumingRequirementIds.clear();
  if (sourceDocumentPollTimer) clearTimeout(sourceDocumentPollTimer);
  sourceDocumentPollTimer = null;
}

/** 轮询指定任务；PENDING/RUNNING 继续，进入终态后刷新需求列表。 */
async function pollExtractionTask(projectId: number, requirementId: number, taskId: number) {
  if (extractionTaskIds.get(requirementId) !== taskId) return;
  const { data, error } = await fetchGetRequirementExtractionTask(projectId, requirementId, taskId);
  if (error) {
    stopExtractionPolling(requirementId);
    return;
  }
  if (data.status === 'PENDING' || data.status === 'RUNNING') {
    const timer = setTimeout(() => {
      void pollExtractionTask(projectId, requirementId, taskId);
    }, 1500);
    extractionPollTimers.set(requirementId, timer);
    return;
  }

  stopExtractionPolling(requirementId);
  if (data.status === 'COMPLETED') {
    window.$message?.success('需求拆解完成，请进入详情校正并确认需求点');
  } else {
    window.$message?.error(data.errorMessage || '需求拆解失败');
  }
  if (activeProjectId.value === projectId) await getData();
}

/** 查询最近活动任务，恢复刷新页面前已经开始的轮询。 */
async function resumeExtractionPolling(row: Api.RequirementManage.Requirement) {
  if (extractionTaskIds.has(row.id) || resumingRequirementIds.has(row.id)) return;
  resumingRequirementIds.add(row.id);
  const { data, error } = await fetchGetLatestRequirementExtractionTask(row.projectId, row.id);
  resumingRequirementIds.delete(row.id);
  if (error || !data || (data.status !== 'PENDING' && data.status !== 'RUNNING')) return;
  extractionTaskIds.set(row.id, data.id);
  await pollExtractionTask(row.projectId, row.id, data.id);
}

async function getFormOptions() {
  if (!activeProjectId.value) return;
  formOptionsLoading.value = true;
  const { data, error } = await fetchGetRequirementFormOptions(activeProjectId.value);
  formOptionsLoading.value = false;
  if (error) return;
  moduleOptions.value = data.modules;
  knowledgeBaseOptions.value = data.knowledgeBases;
  documentOptions.value = data.documents;
  if (
    !sourceKnowledgeBaseId.value ||
    !knowledgeBaseOptions.value.some(item => item.id === sourceKnowledgeBaseId.value)
  ) {
    sourceKnowledgeBaseId.value = knowledgeBaseOptions.value[0]?.id ?? null;
  }
}

function resetForm() {
  Object.assign(form, {
    moduleId: null,
    documentId: null,
    title: '',
    version: '1.0',
    sourceUrl: null,
    summary: ''
  });
  sourceMode.value = 'UPLOAD';
  sourceKnowledgeBaseId.value = null;
  sourceFileList.value = [];
  uploadedSourceDocumentId.value = null;
}

/** 切换来源类型时清理不再适用的值，避免误把旧文档继续提交。 */
function handleSourceModeChange() {
  if (sourceMode.value !== 'EXISTING') form.documentId = null;
  if (sourceMode.value !== 'UPLOAD') {
    sourceFileList.value = [];
    uploadedSourceDocumentId.value = null;
  }
  formRef.value?.clearValidate('summary');
}

/** 换了上传文件后必须重新上传；新建时还可用文件名自动补一个需求标题。 */
function handleSourceFileChange(uploadFile: UploadFile) {
  uploadedSourceDocumentId.value = null;
  if (!editingId.value && !form.title.trim()) {
    form.title = uploadFile.name.replace(/\.[^.]+$/, '');
  }
}

async function openDialog(row?: Api.RequirementManage.Requirement) {
  if (!activeProjectId.value) {
    window.$message?.warning('请先选择项目');
    return;
  }

  editingId.value = row?.id ?? null;
  sourceFileList.value = [];
  uploadedSourceDocumentId.value = null;
  if (row) {
    Object.assign(form, {
      moduleId: row.moduleId,
      documentId: row.documentId,
      title: row.title,
      version: row.version,
      sourceUrl: row.sourceUrl,
      summary: row.summary
    });
    sourceMode.value = row.documentId ? 'EXISTING' : 'MANUAL';
  } else {
    resetForm();
  }
  dialogVisible.value = true;
  await Promise.all([nextTick(), getFormOptions()]);
  formRef.value?.clearValidate();
}

async function submitForm() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !activeProjectId.value) return;

  if (sourceMode.value === 'EXISTING' && !form.documentId) {
    window.$message?.warning('请选择已有需求来源文档');
    return;
  }
  if (sourceMode.value === 'UPLOAD' && !sourceKnowledgeBaseId.value) {
    window.$message?.warning('当前项目没有可用知识库，请先创建并启用知识库');
    return;
  }
  if (sourceMode.value === 'UPLOAD' && !sourceFileList.value[0]?.raw && !uploadedSourceDocumentId.value) {
    window.$message?.warning('请选择需要上传的需求文档');
    return;
  }

  submitting.value = true;
  let documentId = sourceMode.value === 'EXISTING' ? form.documentId : null;
  let uploadedNow = false;

  // 直接上传模式先取得知识文档 ID。后端会同时提交索引任务，随后创建需求时
  // 就能把该 ID 自动写入 document_id，不需要用户再手工选择一次。
  if (sourceMode.value === 'UPLOAD' && !uploadedSourceDocumentId.value) {
    const rawFile = sourceFileList.value[0]?.raw;
    if (!rawFile || !sourceKnowledgeBaseId.value) {
      submitting.value = false;
      return;
    }
    const uploadResult = await fetchUploadRequirementSourceDocument(activeProjectId.value, {
      knowledgeBaseId: sourceKnowledgeBaseId.value,
      file: rawFile,
      title: form.title.trim() || undefined,
      moduleId: form.moduleId ?? undefined,
      metadata: { source: 'requirement_form' }
    });
    if (uploadResult.error) {
      submitting.value = false;
      return;
    }
    uploadedSourceDocumentId.value = uploadResult.data.id;
    uploadedNow = true;
  }
  if (sourceMode.value === 'UPLOAD') documentId = uploadedSourceDocumentId.value;

  const payload: RequirementForm = {
    // ElSelect 被清空后，运行时可能得到 undefined。JSON 会直接忽略
    // undefined 字段，后端便会将其理解为“没有修改”。这里统一转换为
    // null，明确告诉后端清空原来的模块和文档关联。
    moduleId: form.moduleId ?? null,
    documentId: documentId ?? null,
    title: form.title.trim(),
    version: form.version,
    sourceUrl: form.sourceUrl?.trim() || null,
    summary: form.summary?.trim() || ''
  };
  const result = editingId.value
    ? await fetchUpdateRequirement(activeProjectId.value, editingId.value, payload)
    : await fetchCreateRequirement(activeProjectId.value, payload);
  submitting.value = false;
  if (result.error) return;

  dialogVisible.value = false;
  window.$message?.success(
    uploadedNow
      ? `${editingId.value ? '需求已更新' : '需求已创建'}，来源文档正在解析，完成后可启动 AI 拆解`
      : editingId.value
        ? '需求已更新'
        : '需求已创建'
  );
  await getData();
}

async function extractRequirement(row: Api.RequirementManage.Requirement) {
  if (!activeProjectId.value) return;
  const projectId = activeProjectId.value;
  const { data, error } = await fetchExtractRequirement(projectId, row.id);
  if (error) return;
  stopExtractionPolling(row.id);
  extractionTaskIds.set(row.id, data.id);
  window.$message?.success('需求拆解任务已提交');
  await getData();
  await pollExtractionTask(projectId, row.id, data.id);
}

async function deleteRequirement(row: Api.RequirementManage.Requirement) {
  if (!activeProjectId.value) return;
  await ElMessageBox.confirm(`确认删除需求“${row.title}”吗？`, '删除需求', { type: 'warning' });
  const { error } = await fetchDeleteRequirement(activeProjectId.value, row.id);
  if (error) return;
  if (records.value.length === 1 && searchParams.current > 1) searchParams.current -= 1;
  window.$message?.success('需求已删除');
  await getData();
}

function openDetail(row: Api.RequirementManage.Requirement) {
  void router.push({
    path: '/requirement/detail',
    query: { projectId: row.projectId, requirementId: row.id }
  });
}

async function handleProjectChange() {
  stopAllExtractionPolling();
  searchParams.current = 1;
  await getData();
}

const handleSearch = useDebounceFn(() => {
  searchParams.current = 1;
  void getData();
}, 300);

async function handleStatusChange() {
  searchParams.current = 1;
  await getData();
}

async function init() {
  await getProjects();
  await getData();
}

void init();
onBeforeUnmount(stopAllExtractionPolling);
</script>

<template>
  <div class="requirement-page">
    <ElCard class="requirement-card">
      <template #header>
        <div class="requirement-header">
          <div class="requirement-heading">
            <h2>需求管理</h2>
            <p>维护需求版本和来源内容，拆解后进入人工确认与覆盖分析</p>
          </div>
          <div class="requirement-header-actions">
            <ElButton @click="getData">
              <SvgIcon icon="mdi:refresh" />
              刷新
            </ElButton>
            <ElButton v-if="canManage" type="primary" @click="openDialog()">
              <SvgIcon icon="mdi:plus" />
              新建需求
            </ElButton>
          </div>
        </div>
      </template>

      <div class="requirement-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-select"
          filterable
          :loading="projectLoading"
          placeholder="选择项目"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElInput
          v-model="searchParams.keyword"
          class="search-input"
          clearable
          placeholder="搜索需求标题或来源地址"
          @input="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><SvgIcon icon="mdi:magnify" /></template>
        </ElInput>
        <ElSelect v-model="searchParams.status" clearable placeholder="全部状态" @change="handleStatusChange">
          <ElOption
            v-for="item in requirementStatusOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </ElSelect>
      </div>

      <div v-if="!isMobile" class="requirement-table-wrap">
        <ElTable v-loading="loading" height="100%" border :data="records" row-key="id">
          <ElTableColumn label="需求" min-width="310">
            <template #default="{ row }: { row: Api.RequirementManage.Requirement }">
              <div class="requirement-title-cell">
                <span class="requirement-title-icon"><SvgIcon icon="mdi:file-document-edit-outline" /></span>
                <span class="requirement-title-copy">
                  <strong>{{ row.title }}</strong>
                  <small>版本 V{{ row.version }} · {{ row.documentTitle || '手工录入' }}</small>
                  <ElTag
                    v-if="sourceDocumentStatusLabel(row)"
                    :type="row.documentParseStatus === 'FAILED' ? 'danger' : 'warning'"
                    size="small"
                  >
                    {{ sourceDocumentStatusLabel(row) }}
                  </ElTag>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="moduleName" label="功能模块" min-width="140">
            <template #default="{ row }">{{ row.moduleName || '全部模块' }}</template>
          </ElTableColumn>
          <ElTableColumn label="需求点确认" width="180">
            <template #default="{ row }: { row: Api.RequirementManage.Requirement }">
              <div class="requirement-progress">
                <span>{{ row.confirmedItemCount }} / {{ row.itemCount }}</span>
                <ElProgress
                  :percentage="row.itemCount ? Math.round((row.confirmedItemCount / row.itemCount) * 100) : 0"
                  :show-text="false"
                  :stroke-width="6"
                />
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="104" align="center">
            <template #default="{ row }: { row: Api.RequirementManage.Requirement }">
              <ElTag :type="requirementStatusType(row.status)" effect="light">
                {{ requirementStatusLabel(row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="创建人" width="120">
            <template #default="{ row }">{{ row.createdByName || '-' }}</template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" width="155">
            <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="170" align="center" fixed="right">
            <template #default="{ row }: { row: Api.RequirementManage.Requirement }">
              <ElButton text circle title="查看需求点" @click="openDetail(row)">
                <SvgIcon icon="mdi:eye-outline" />
              </ElButton>
              <ElButton
                v-if="canExtract"
                text
                circle
                :disabled="!canStartExtraction(row)"
                :title="extractionButtonTitle(row)"
                @click="extractRequirement(row)"
              >
                <SvgIcon icon="mdi:creation-outline" />
              </ElButton>
              <ElButton v-if="canManage" text circle title="编辑" @click="openDialog(row)">
                <SvgIcon icon="mdi:pencil-outline" />
              </ElButton>
              <ElButton v-if="canManage" text circle type="danger" title="删除" @click="deleteRequirement(row)">
                <SvgIcon icon="mdi:delete-outline" />
              </ElButton>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前项目暂无需求" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else v-loading="loading" class="requirement-mobile-list">
        <article v-for="row in records" :key="row.id" class="requirement-mobile-card">
          <div class="requirement-mobile-head">
            <ElTag :type="requirementStatusType(row.status)" size="small">
              {{ requirementStatusLabel(row.status) }}
            </ElTag>
            <span class="requirement-muted">V{{ row.version }}</span>
          </div>
          <h3>{{ row.title }}</h3>
          <p>{{ row.moduleName || '全部模块' }} · 已确认 {{ row.confirmedItemCount }}/{{ row.itemCount }}</p>
          <div class="requirement-mobile-foot">
            <span>{{ dayjs(row.updatedAt).format('MM-DD HH:mm') }}</span>
            <div class="requirement-inline-actions">
              <ElButton text size="small" @click="openDetail(row)">详情</ElButton>
              <ElButton v-if="canManage" text size="small" @click="openDialog(row)">编辑</ElButton>
            </div>
          </div>
        </article>
        <ElEmpty v-if="!records.length && !loading" description="当前项目暂无需求" :image-size="72" />
      </div>

      <footer class="requirement-footer">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, prev, pager, next, sizes"
          @current-change="getData"
          @size-change="
            searchParams.current = 1;
            getData();
          "
        />
      </footer>
    </ElCard>

    <ElDrawer v-model="dialogVisible" :title="dialogTitle" :size="isMobile ? '100%' : '520px'" destroy-on-close>
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="需求标题" prop="title">
          <ElInput v-model="form.title" maxlength="300" show-word-limit placeholder="例如：文章发布与下线需求" />
        </ElFormItem>
        <div class="form-grid">
          <ElFormItem label="所属模块">
            <ElSelect
              v-model="form.moduleId"
              clearable
              filterable
              :loading="formOptionsLoading"
              placeholder="不限定模块"
            >
              <ElOption v-for="item in moduleOptions" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="需求版本" prop="version">
            <ElInput v-model="form.version" maxlength="40" placeholder="例如 1.0、1.1 或 2026.08" />
          </ElFormItem>
        </div>

        <ElFormItem label="需求来源" required>
          <ElRadioGroup v-model="sourceMode" class="source-mode-group" @change="handleSourceModeChange">
            <ElRadioButton value="UPLOAD">上传需求文档</ElRadioButton>
            <ElRadioButton value="EXISTING">选择已有需求文档</ElRadioButton>
            <ElRadioButton value="MANUAL">手工录入</ElRadioButton>
          </ElRadioGroup>
          <div class="source-help">选择需要进行 AI 拆解的需求文档；不选择时，将使用需求摘要进行拆解。</div>
        </ElFormItem>

        <template v-if="sourceMode === 'UPLOAD'">
          <ElFormItem label="保存到知识库" required>
            <ElSelect
              v-model="sourceKnowledgeBaseId"
              filterable
              :loading="formOptionsLoading"
              placeholder="请选择用于保存需求文档的知识库"
            >
              <ElOption v-for="item in knowledgeBaseOptions" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="上传需求文档" required>
            <ElUpload
              v-model:file-list="sourceFileList"
              class="source-upload"
              drag
              :auto-upload="false"
              :limit="1"
              accept=".pdf,.docx,.md,.txt"
              @change="handleSourceFileChange"
            >
              <icon-ep-upload-filled class="source-upload-icon" />
              <div class="el-upload__text">
                将文件拖到此处，或
                <em>点击选择</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">支持 PDF、DOCX、Markdown、TXT；保存需求后会自动关联并在后台解析。</div>
              </template>
            </ElUpload>
          </ElFormItem>
        </template>

        <ElFormItem v-else-if="sourceMode === 'EXISTING'" label="需求来源文档" required>
          <ElSelect
            v-model="form.documentId"
            clearable
            filterable
            :loading="formOptionsLoading"
            placeholder="请选择已经解析完成的需求文档"
          >
            <ElOption
              v-for="item in documentOptions"
              :key="item.id"
              :label="`${item.title} · V${item.version}`"
              :value="item.id"
            />
          </ElSelect>
        </ElFormItem>

        <ElAlert v-else type="info" :closable="false" show-icon class="manual-source-alert">
          不关联文件，AI 将使用下面填写的需求摘要作为拆解正文。
        </ElAlert>

        <ElFormItem :label="sourceMode === 'MANUAL' ? '需求摘要' : '需求摘要（可选）'" prop="summary">
          <ElInput
            v-model="form.summary"
            type="textarea"
            :rows="4"
            maxlength="20000"
            show-word-limit
            :placeholder="sourceMode === 'MANUAL' ? '请完整填写需要进行 AI 拆解的需求内容' : '可填写文档之外的补充说明'"
          />
        </ElFormItem>
        <ElFormItem label="外部来源地址">
          <ElInput
            v-model="form.sourceUrl"
            clearable
            maxlength="1000"
            placeholder="例如 Jira、禅道或在线需求文档地址"
          />
        </ElFormItem>
        <ElAlert type="info" :closable="false" show-icon>
          创建后可启动 AI 拆解；拆解结果必须经过人工确认，才能进入覆盖分析和用例生成。
        </ElAlert>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">确认</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 130px;
  gap: 12px;
}

.source-mode-group {
  display: flex;
  width: 100%;

  :deep(.el-radio-button) {
    flex: 1;
  }

  :deep(.el-radio-button__inner) {
    width: 100%;
  }
}

.source-upload {
  width: 100%;

  :deep(.el-upload),
  :deep(.el-upload-dragger) {
    width: 100%;
  }
}

.source-upload-icon {
  margin-bottom: 8px;
  color: var(--el-text-color-placeholder);
  font-size: 42px;
}

.source-help {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.manual-source-alert {
  margin-bottom: 18px;
}

@media (max-width: 700px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .source-mode-group {
    display: grid;
    grid-template-columns: 1fr;
  }
}
</style>
