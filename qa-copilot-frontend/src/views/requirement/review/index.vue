<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useMediaQuery } from '@vueuse/core';
import dayjs from 'dayjs';
import {
  fetchBatchReviewGeneratedCases,
  fetchGetGenerationTaskList,
  fetchGetProjectList,
  fetchReviewGeneratedCase
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'CaseGenerationReview' });

const authStore = useAuthStore();
const route = useRoute();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const reviewing = ref(false);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const records = ref<Api.RequirementManage.GenerationTask[]>([]);
const total = ref(0);
const expandedTaskIds = ref<number[]>([]);
const reviewDialogVisible = ref(false);
const activeCase = ref<Api.RequirementManage.TestCase | null>(null);
const reviewMode = ref<'single' | 'batch'>('single');
const selectedCaseIds = ref<number[]>([]);
const reviewForm = reactive<Api.RequirementManage.CaseReviewParams>({ action: 'ACCEPT', comment: '' });
let pollingTimer: ReturnType<typeof setInterval> | null = null;

const searchParams = reactive<Api.RequirementManage.GenerationTaskSearchParams>({
  current: 1,
  size: 10,
  requirementId: undefined,
  status: undefined
});

// 从覆盖分析页跳转时保留项目和需求过滤条件，直接展示刚提交的任务。
activeProjectId.value = Number(route.query.projectId) || null;
searchParams.requirementId = Number(route.query.requirementId) || undefined;

const canReview = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('test:case:review');
});
const hasRunningTask = computed(() =>
  records.value.some(item => item.status === 'PENDING' || item.status === 'RUNNING')
);
const batchSelectableCases = computed(() =>
  records.value
    .flatMap(item => item.draftCases ?? [])
    .filter(item => ['DRAFT', 'REVIEWING', 'APPROVED', 'REJECTED'].includes(item.status))
);
const allSelectableSelected = computed(
  () =>
    batchSelectableCases.value.length > 0 &&
    batchSelectableCases.value.every(item => selectedCaseIds.value.includes(item.id))
);
const selectionIndeterminate = computed(() => selectedCaseIds.value.length > 0 && !allSelectableSelected.value);

function taskStatusLabel(status: Api.RequirementManage.GenerationTaskStatus) {
  return {
    PENDING: '等待执行',
    RUNNING: '生成中',
    WAITING_REVIEW: '待审核',
    COMPLETED: '已完成',
    FAILED: '失败',
    CANCELLED: '已取消'
  }[status];
}

function taskStatusType(status: Api.RequirementManage.GenerationTaskStatus) {
  return {
    PENDING: 'info',
    RUNNING: 'primary',
    WAITING_REVIEW: 'warning',
    COMPLETED: 'success',
    FAILED: 'danger',
    CANCELLED: 'info'
  }[status] as 'info' | 'primary' | 'warning' | 'success' | 'danger';
}

async function getProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getData(silent = false) {
  if (!activeProjectId.value) return;
  if (!silent) loading.value = true;
  const { data, error } = await fetchGetGenerationTaskList(activeProjectId.value, searchParams);
  loading.value = false;
  if (!error) {
    records.value = data.records;
    total.value = data.total;
    // 分页、筛选或轮询刷新后，移除当前页面已不存在的选择，避免误操作旧 ID。
    const visibleIds = new Set(data.records.flatMap(item => item.draftCases ?? []).map(item => item.id));
    selectedCaseIds.value = selectedCaseIds.value.filter(id => visibleIds.has(id));
  }
}

function restartPolling() {
  if (pollingTimer) clearInterval(pollingTimer);
  pollingTimer = setInterval(() => {
    if (hasRunningTask.value) void getData(true);
  }, 4000);
}

async function handleProjectChange() {
  searchParams.current = 1;
  expandedTaskIds.value = [];
  selectedCaseIds.value = [];
  await getData();
}

function openReview(testCase: Api.RequirementManage.TestCase, action: Api.RequirementManage.ReviewAction) {
  reviewMode.value = 'single';
  activeCase.value = testCase;
  reviewForm.action = action;
  reviewForm.comment = '';
  reviewDialogVisible.value = true;
}

/** 判断当前批量动作是否适用于所有已选用例，避免请求后才发现整批回滚。 */
function validateBatchSelection(action: Api.RequirementManage.ReviewAction) {
  const allowedStatuses: Partial<Record<Api.RequirementManage.ReviewAction, Api.RequirementManage.TestCaseStatus[]>> = {
    ACCEPT: ['DRAFT', 'REVIEWING', 'REJECTED'],
    REJECT: ['DRAFT', 'REVIEWING', 'APPROVED'],
    PUBLISH: ['APPROVED']
  };
  const selected = batchSelectableCases.value.filter(item => selectedCaseIds.value.includes(item.id));
  const allowed = allowedStatuses[action] ?? [];
  const invalidCases = selected.filter(item => !allowed.includes(item.status));
  if (invalidCases.length) {
    window.$message?.warning(`${invalidCases.length} 条已选用例的当前状态不允许执行该动作，请调整选择后重试`);
    return false;
  }
  return selected.length > 0;
}

/** 打开批量审核确认框；这里只收集动作和统一意见，真正校验仍由后端状态机完成。 */
function openBatchReview(action: 'ACCEPT' | 'REJECT' | 'PUBLISH') {
  if (!selectedCaseIds.value.length) {
    window.$message?.warning('请先选择需要处理的测试用例');
    return;
  }
  if (!validateBatchSelection(action)) return;
  reviewMode.value = 'batch';
  activeCase.value = null;
  reviewForm.action = action;
  reviewForm.comment = '';
  reviewDialogVisible.value = true;
}

function toggleCaseSelection(testCaseId: number, checked: boolean) {
  if (checked) {
    if (!selectedCaseIds.value.includes(testCaseId)) selectedCaseIds.value.push(testCaseId);
    return;
  }
  selectedCaseIds.value = selectedCaseIds.value.filter(id => id !== testCaseId);
}

function toggleSelectAll(checked: boolean) {
  selectedCaseIds.value = checked ? batchSelectableCases.value.map(item => item.id) : [];
}

async function submitReview() {
  if (!activeProjectId.value) return;
  if (reviewMode.value === 'batch' && !validateBatchSelection(reviewForm.action)) return;
  if (reviewMode.value === 'single' && !activeCase.value) return;
  reviewing.value = true;
  const payload = { action: reviewForm.action, comment: reviewForm.comment.trim() };
  const { error } =
    reviewMode.value === 'batch'
      ? await fetchBatchReviewGeneratedCases(activeProjectId.value, {
          ...payload,
          testCaseIds: selectedCaseIds.value
        })
      : await fetchReviewGeneratedCase(activeProjectId.value, activeCase.value!.id, payload);
  reviewing.value = false;
  if (error) return;
  reviewDialogVisible.value = false;
  if (reviewMode.value === 'batch') selectedCaseIds.value = [];
  window.$message?.success(reviewMode.value === 'batch' ? '批量审核结果已保存' : '审核结果已保存');
  await getData();
}

async function init() {
  await getProjects();
  await getData();
  restartPolling();
}

onBeforeUnmount(() => {
  if (pollingTimer) clearInterval(pollingTimer);
});

void init();
</script>

<template>
  <div class="requirement-page review-page">
    <ElCard class="requirement-card">
      <template #header>
        <div class="requirement-header">
          <div class="requirement-heading">
            <h2>用例生成与审核</h2>
            <p>查看生成进度，对 AI 草稿执行接受、修改、驳回、判重和发布</p>
          </div>
          <div class="requirement-header-actions">
            <ElButton @click="getData()">
              <SvgIcon icon="mdi:refresh" />
              刷新
            </ElButton>
          </div>
        </div>
      </template>

      <div class="requirement-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-select"
          filterable
          placeholder="选择项目"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElSelect v-model="searchParams.status" clearable placeholder="全部任务状态" @change="getData()">
          <ElOption label="等待执行" value="PENDING" />
          <ElOption label="生成中" value="RUNNING" />
          <ElOption label="待审核" value="WAITING_REVIEW" />
          <ElOption label="已完成" value="COMPLETED" />
          <ElOption label="已取消" value="CANCELLED" />
          <ElOption label="失败" value="FAILED" />
        </ElSelect>
        <span v-if="hasRunningTask" class="polling-tip">
          <i />
          正在自动刷新运行中的任务
        </span>
      </div>

      <div v-if="canReview && batchSelectableCases.length" class="batch-review-bar">
        <ElCheckbox
          :model-value="allSelectableSelected"
          :indeterminate="selectionIndeterminate"
          @change="toggleSelectAll(Boolean($event))"
        >
          全选当前页
        </ElCheckbox>
        <span>已选择 {{ selectedCaseIds.length }} 条</span>
        <div class="batch-review-actions">
          <ElButton :disabled="!selectedCaseIds.length" type="success" @click="openBatchReview('ACCEPT')">
            批量接受
          </ElButton>
          <ElButton :disabled="!selectedCaseIds.length" type="danger" @click="openBatchReview('REJECT')">
            批量驳回
          </ElButton>
          <ElButton :disabled="!selectedCaseIds.length" type="primary" @click="openBatchReview('PUBLISH')">
            批量发布
          </ElButton>
          <ElButton :disabled="!selectedCaseIds.length" @click="selectedCaseIds = []">清空选择</ElButton>
        </div>
      </div>

      <div v-loading="loading" class="task-list">
        <article v-for="task in records" :key="task.id" class="task-card">
          <header class="task-head">
            <div class="task-title">
              <span class="task-icon"><SvgIcon icon="mdi:creation-outline" /></span>
              <div>
                <strong>{{ task.requirementTitle || `需求 #${task.requirementId}` }}</strong>
                <small>任务 #{{ task.id }} · {{ dayjs(task.createdAt).format('YYYY-MM-DD HH:mm') }}</small>
              </div>
            </div>
            <ElTag :type="taskStatusType(task.status)">{{ taskStatusLabel(task.status) }}</ElTag>
          </header>
          <div class="task-progress">
            <ElProgress
              :percentage="task.progress"
              :status="task.status === 'FAILED' ? 'exception' : task.status === 'COMPLETED' ? 'success' : undefined"
            />
            <span>{{ task.draftCases?.length || 0 }} 条草稿用例</span>
          </div>
          <ElAlert v-if="task.errorMessage" type="error" :closable="false" :title="task.errorMessage" show-icon />

          <div v-if="task.draftCases?.length" class="draft-list">
            <article v-for="testCase in task.draftCases" :key="testCase.id" class="draft-card">
              <div class="draft-main">
                <ElCheckbox
                  v-if="canReview && ['DRAFT', 'REVIEWING', 'APPROVED', 'REJECTED'].includes(testCase.status)"
                  :model-value="selectedCaseIds.includes(testCase.id)"
                  :aria-label="`选择用例 ${testCase.caseCode || testCase.id}`"
                  @change="toggleCaseSelection(testCase.id, Boolean($event))"
                />
                <div class="draft-title">
                  <strong>{{ testCase.caseCode }} · {{ testCase.title }}</strong>
                  <span>
                    {{ testCase.priority }} · {{ testCase.steps.length }} 个步骤 ·
                    {{ testCase.moduleName || '未关联模块' }}
                  </span>
                </div>
                <ElTag
                  :type="
                    testCase.status === 'REJECTED' ? 'danger' : testCase.status === 'PUBLISHED' ? 'success' : 'warning'
                  "
                  size="small"
                >
                  {{ testCase.status }}
                </ElTag>
              </div>
              <div
                v-if="canReview && ['DRAFT', 'REVIEWING', 'APPROVED'].includes(testCase.status)"
                class="draft-actions"
              >
                <ElButton text type="success" @click="openReview(testCase, 'ACCEPT')">接受</ElButton>
                <ElButton text @click="openReview(testCase, 'MODIFY')">修改</ElButton>
                <ElButton text type="danger" @click="openReview(testCase, 'REJECT')">驳回</ElButton>
                <ElButton text @click="openReview(testCase, 'DUPLICATE')">标记重复</ElButton>
                <ElButton
                  text
                  type="primary"
                  :disabled="testCase.status !== 'APPROVED'"
                  @click="openReview(testCase, 'PUBLISH')"
                >
                  发布
                </ElButton>
              </div>
            </article>
          </div>
        </article>
        <ElEmpty
          v-if="!records.length && !loading"
          description="暂无用例生成任务，可从覆盖分析提交缺失用例生成"
          :image-size="82"
        />
      </div>

      <footer class="requirement-footer">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :page-sizes="[10, 20, 30]"
          layout="total, prev, pager, next, sizes"
          @current-change="getData()"
          @size-change="
            searchParams.current = 1;
            getData();
          "
        />
      </footer>
    </ElCard>

    <ElDialog
      v-model="reviewDialogVisible"
      :title="
        reviewMode === 'batch' ? `批量审核 ${selectedCaseIds.length} 条用例` : `审核用例：${activeCase?.caseCode || ''}`
      "
      :width="isMobile ? '94%' : '520px'"
    >
      <ElForm label-position="top">
        <ElFormItem label="审核动作">
          <ElSelect v-model="reviewForm.action">
            <ElOption label="接受" value="ACCEPT" />
            <ElOption v-if="reviewMode === 'single'" label="修改后接受" value="MODIFY" />
            <ElOption label="驳回" value="REJECT" />
            <ElOption v-if="reviewMode === 'single'" label="标记重复" value="DUPLICATE" />
            <ElOption label="发布" value="PUBLISH" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="审核意见">
          <ElInput
            v-model="reviewForm.comment"
            type="textarea"
            :rows="4"
            maxlength="2000"
            show-word-limit
            placeholder="说明接受依据、修改内容或驳回原因"
          />
        </ElFormItem>
        <ElAlert v-if="reviewForm.action === 'MODIFY'" type="info" :closable="false">
          保存审核动作后，请在“测试用例管理”中编辑具体字段和步骤。
        </ElAlert>
      </ElForm>
      <template #footer>
        <ElButton @click="reviewDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="reviewing" @click="submitReview">确认审核</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.polling-tip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.polling-tip i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--el-color-primary);
  animation: pulse 1.4s infinite;
}
.task-list {
  min-height: 390px;
  padding: 14px 16px;
}
.batch-review-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 12px 16px 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-light);
  padding: 10px 12px;
}
.batch-review-bar > span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.batch-review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}
.task-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px;
}
.task-card + .task-card {
  margin-top: 12px;
}
.task-head,
.task-title,
.task-progress,
.draft-main,
.draft-actions {
  display: flex;
  align-items: center;
}
.task-head,
.draft-main {
  justify-content: space-between;
  gap: 12px;
}
.draft-title {
  min-width: 0;
  flex: 1;
}
.task-title {
  gap: 10px;
}
.task-title div,
.task-title small,
.draft-title span {
  display: block;
}
.task-title small,
.draft-title span {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.task-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: rgb(var(--primary-color) / 9%);
  color: rgb(var(--primary-color));
  font-size: 19px;
}
.task-progress {
  gap: 16px;
  margin-top: 13px;
}
.task-progress .el-progress {
  flex: 1;
}
.task-progress > span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.draft-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light);
  padding-top: 12px;
}
.draft-card {
  border: 1px solid var(--el-border-color-extra-light);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
  padding: 10px 12px;
}
.draft-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-top: 7px;
}
@keyframes pulse {
  50% {
    opacity: 0.3;
    transform: scale(0.7);
  }
}
@media (max-width: 700px) {
  .task-head,
  .draft-main,
  .task-progress {
    align-items: flex-start;
    flex-direction: column;
  }
  .batch-review-bar {
    align-items: flex-start;
    flex-direction: column;
  }
  .batch-review-actions {
    margin-left: 0;
  }
  .task-progress .el-progress {
    width: 100%;
  }
  .draft-actions {
    justify-content: flex-start;
  }
}
</style>
