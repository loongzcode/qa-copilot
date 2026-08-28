<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue';
import { useDebounceFn, useMediaQuery } from '@vueuse/core';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCloneTestCaseAsDraft,
  fetchCreateTestCase,
  fetchDeleteTestCase,
  fetchGetProjectList,
  fetchGetProjectModules,
  fetchGetTestCaseDetail,
  fetchGetTestCaseList,
  fetchGetTestCaseRequirementItemOptions,
  fetchReviewGeneratedCase,
  fetchUpdateTestCase
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import { createAutomationStepTemplateText, getAutomationIneligibleReason } from '@/utils/automation-test-case';
import { flattenModules, priorityOptions, testCaseTypeOptions } from '../shared';
import AutomationStepEditor from './components/automation-step-editor.vue';

defineOptions({ name: 'TestCaseList' });

type CaseFormStep = Omit<Api.RequirementManage.TestCaseCreateParams['steps'][number], 'testData'> & {
  testData: string;
};
type CaseForm = Omit<Api.RequirementManage.TestCaseCreateParams, 'caseCode' | 'steps'> & {
  caseCode: string;
  steps: CaseFormStep[];
};

const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const submitting = ref(false);
const detailLoading = ref(false);
const drawerVisible = ref(false);
const editingId = ref<number | null>(null);
const automationRevisionSourceId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const modules = ref<Array<{ id: number; name: string }>>([]);
const records = ref<Api.RequirementManage.TestCase[]>([]);
const requirementItemOptions = ref<Api.RequirementManage.TestCaseRequirementItemOption[]>([]);
const total = ref(0);
const formRef = ref<FormInstance>();

const searchParams = reactive<Api.RequirementManage.TestCaseSearchParams>({
  current: 1,
  size: 10,
  keyword: '',
  moduleId: undefined,
  status: undefined,
  source: undefined
});

const form = reactive<CaseForm>({
  moduleId: null,
  caseCode: '',
  title: '',
  caseType: 'FUNCTIONAL',
  priority: 'P2',
  preconditions: '',
  expectedSummary: '',
  automatable: false,
  version: 1,
  steps: [{ stepNo: 1, action: '', testData: '', expectedResult: '' }],
  requirementItemIds: []
});

const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('test:case:manage');
});
const canReview = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('test:case:review');
});

const rules: FormRules<CaseForm> = {
  caseCode: [{ required: true, message: '请输入用例编码', trigger: 'blur' }],
  title: [{ required: true, message: '请输入用例标题', trigger: 'blur' }],
  caseType: [{ required: true, message: '请选择测试类型', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }]
};

function caseTypeLabel(type: Api.RequirementManage.TestCaseType) {
  return testCaseTypeOptions.find(item => item.value === type)?.label ?? type;
}

function statusLabel(status: Api.RequirementManage.TestCaseStatus) {
  return {
    DRAFT: '草稿',
    REVIEWING: '审核中',
    APPROVED: '已接受',
    REJECTED: '已驳回',
    PUBLISHED: '已发布',
    DISABLED: '已停用'
  }[status];
}

function statusType(status: Api.RequirementManage.TestCaseStatus) {
  return {
    DRAFT: 'info',
    REVIEWING: 'warning',
    APPROVED: 'success',
    REJECTED: 'danger',
    PUBLISHED: 'primary',
    DISABLED: 'info'
  }[status] as 'info' | 'warning' | 'success' | 'danger' | 'primary';
}

async function getProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getModules() {
  if (!activeProjectId.value) return;
  const { data, error } = await fetchGetProjectModules(activeProjectId.value, { keyword: '' });
  if (!error) modules.value = flattenModules(data);
}

async function getRequirementItemOptions() {
  requirementItemOptions.value = [];
  if (!activeProjectId.value) return;
  const { data, error } = await fetchGetTestCaseRequirementItemOptions(activeProjectId.value);
  if (!error) requirementItemOptions.value = data;
}

async function getData() {
  if (!activeProjectId.value) return;
  loading.value = true;
  const { data, error } = await fetchGetTestCaseList(activeProjectId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;
  if (!error) {
    records.value = data.records;
    total.value = data.total;
  }
}

async function handleProjectChange() {
  searchParams.current = 1;
  searchParams.moduleId = undefined;
  modules.value = [];
  await Promise.all([getModules(), getRequirementItemOptions(), getData()]);
}

const handleSearch = useDebounceFn(() => {
  searchParams.current = 1;
  void getData();
}, 300);

function resetForm() {
  Object.assign(form, {
    moduleId: null,
    caseCode: '',
    title: '',
    caseType: 'FUNCTIONAL',
    priority: 'P2',
    preconditions: '',
    expectedSummary: '',
    automatable: false,
    version: 1,
    steps: [{ stepNo: 1, action: '', testData: '', expectedResult: '' }],
    requirementItemIds: []
  });
}

async function openDrawer(row?: Api.RequirementManage.TestCase) {
  automationRevisionSourceId.value = null;
  editingId.value = row?.id ?? null;
  if (!row) {
    resetForm();
  } else if (activeProjectId.value) {
    detailLoading.value = true;
    const { data, error } = await fetchGetTestCaseDetail(activeProjectId.value, row.id);
    detailLoading.value = false;
    if (error) return;
    Object.assign(form, {
      moduleId: data.moduleId,
      caseCode: data.caseCode || '',
      title: data.title,
      caseType: data.caseType,
      priority: data.priority,
      preconditions: data.preconditions,
      expectedSummary: data.expectedSummary,
      automatable: data.automatable,
      version: data.version,
      steps: data.steps.map(step => ({
        stepNo: step.stepNo,
        action: step.action,
        testData:
          step.testData == null
            ? ''
            : typeof step.testData === 'string'
              ? step.testData
              : JSON.stringify(step.testData, null, 2),
        expectedResult: step.expectedResult
      })),
      requirementItemIds: data.requirementItemIds || []
    });
  }
  drawerVisible.value = true;
  await nextTick();
  formRef.value?.clearValidate();
}

/**
 * 为不可修改的发布版本创建新草稿，并直接进入接口自动化修正状态。
 * 旧版本继续保留审计关系，新草稿可以安全修改类型、请求和断言。
 */
async function cloneAsAutomationDraft(row: Api.RequirementManage.TestCase) {
  if (!activeProjectId.value) return;
  detailLoading.value = true;
  const { data, error } = await fetchCloneTestCaseAsDraft(activeProjectId.value, row.id);
  detailLoading.value = false;
  if (error) return;

  await openDrawer(data);
  automationRevisionSourceId.value = row.id;
  form.caseType = 'API';
  form.automatable = true;
  // 自然语言步骤没有 request/assertions 时先填入最小模板。用户只需修改请求方法、
  // 路径和预期断言，不需要从空白 JSON 开始编写。
  form.steps.forEach(step => {
    const parsed = parseTestData(step.testData);
    const hasProtocol =
      parsed !== null &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed) &&
      'request' in parsed &&
      'assertions' in parsed;
    if (!hasProtocol) step.testData = createAutomationStepTemplateText();
  });
  window.$message?.success('已创建可编辑草稿，请修改接口路径和断言后保存、接受并发布');
  await getData();
}

function addStep() {
  form.steps.push({ stepNo: form.steps.length + 1, action: '', testData: '', expectedResult: '' });
}

function removeStep(index: number) {
  if (form.steps.length === 1) {
    window.$message?.warning('测试用例至少保留一个步骤');
    return;
  }
  form.steps.splice(index, 1);
  form.steps.forEach((step, stepIndex) => {
    step.stepNo = stepIndex + 1;
  });
}

async function submitCase() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !activeProjectId.value) return;
  if (form.steps.some(step => !step.action.trim() || !step.expectedResult.trim())) {
    window.$message?.warning('每个步骤都必须填写操作和预期结果');
    return;
  }

  const payload: Api.RequirementManage.TestCaseCreateParams = {
    ...form,
    caseCode: form.caseCode.trim(),
    title: form.title.trim(),
    preconditions: form.preconditions.trim(),
    expectedSummary: form.expectedSummary.trim(),
    steps: form.steps.map(step => ({
      ...step,
      action: step.action.trim(),
      // 数据库字段是 JSONB：合法 JSON 转为对象/数组，普通文本则作为 JSON 字符串保存。
      testData: parseTestData(step.testData),
      expectedResult: step.expectedResult.trim()
    }))
  };
  submitting.value = true;
  const result = editingId.value
    ? await fetchUpdateTestCase(activeProjectId.value, editingId.value, payload)
    : await fetchCreateTestCase(activeProjectId.value, payload);
  submitting.value = false;
  if (result.error) return;
  drawerVisible.value = false;
  window.$message?.success(editingId.value ? '用例已更新' : '用例已创建');
  await getData();
}

function parseTestData(value: string): unknown | null {
  const text = value.trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function deleteCase(row: Api.RequirementManage.TestCase) {
  if (!activeProjectId.value) return;
  await ElMessageBox.confirm(`确认删除用例“${row.caseCode} ${row.title}”吗？`, '删除用例', { type: 'warning' });
  const { error } = await fetchDeleteTestCase(activeProjectId.value, row.id);
  if (error) return;
  window.$message?.success('测试用例已删除');
  await getData();
}

async function changeCaseStatus(row: Api.RequirementManage.TestCase, action: Api.RequirementManage.ReviewAction) {
  if (!activeProjectId.value) return;
  if (action === 'PUBLISH' && row.automatable) {
    const reason = getAutomationIneligibleReason(row);
    if (reason) {
      window.$message?.warning(
        `暂时不能发布为自动化用例：${reason}。请先编辑；如果已经发布，请使用“创建自动化版本”生成草稿后修正。`
      );
      return;
    }
  }
  const actionLabels: Partial<Record<Api.RequirementManage.ReviewAction, string>> = {
    ACCEPT: '接受',
    PUBLISH: '发布',
    DISABLE: '停用'
  };
  const actionLabel = actionLabels[action] || action;
  await ElMessageBox.confirm(`确认${actionLabel}用例“${row.caseCode || ''} ${row.title}”吗？`, `${actionLabel}用例`, {
    type: 'warning'
  });
  const { error } = await fetchReviewGeneratedCase(activeProjectId.value, row.id, {
    action,
    comment: `${actionLabel}测试用例`
  });
  if (error) return;
  window.$message?.success(`用例已${actionLabel}`);
  await getData();
}

async function init() {
  await getProjects();
  await Promise.all([getModules(), getRequirementItemOptions(), getData()]);
}

void init();
</script>

<template>
  <div class="requirement-page">
    <ElCard class="requirement-card">
      <template #header>
        <div class="requirement-header">
          <div class="requirement-heading">
            <h2>测试用例管理</h2>
            <p>统一维护人工、AI 和导入用例，以及结构化步骤和发布状态</p>
          </div>
          <div class="requirement-header-actions">
            <ElButton @click="getData">
              <SvgIcon icon="mdi:refresh" />
              刷新
            </ElButton>
            <ElButton v-if="canManage" type="primary" @click="openDrawer()">
              <SvgIcon icon="mdi:plus" />
              新建用例
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
        <ElInput
          v-model="searchParams.keyword"
          class="search-input"
          clearable
          placeholder="搜索用例编码或标题"
          @input="handleSearch"
        >
          <template #prefix><SvgIcon icon="mdi:magnify" /></template>
        </ElInput>
        <ElSelect v-model="searchParams.moduleId" clearable placeholder="全部模块" @change="getData">
          <ElOption v-for="item in modules" :key="item.id" :label="item.name" :value="item.id" />
        </ElSelect>
        <ElSelect v-model="searchParams.status" clearable placeholder="全部状态" @change="getData">
          <ElOption label="草稿" value="DRAFT" />
          <ElOption label="审核中" value="REVIEWING" />
          <ElOption label="已接受" value="APPROVED" />
          <ElOption label="已驳回" value="REJECTED" />
          <ElOption label="已发布" value="PUBLISHED" />
          <ElOption label="已停用" value="DISABLED" />
        </ElSelect>
        <ElSelect v-model="searchParams.source" clearable placeholder="全部来源" @change="getData">
          <ElOption label="人工" value="MANUAL" />
          <ElOption label="AI 生成" value="AI_GENERATED" />
          <ElOption label="导入" value="IMPORTED" />
        </ElSelect>
      </div>

      <div v-if="!isMobile" class="requirement-table-wrap">
        <ElTable v-loading="loading" height="100%" border :data="records" row-key="id">
          <ElTableColumn label="用例" min-width="330">
            <template #default="{ row }: { row: Api.RequirementManage.TestCase }">
              <div class="requirement-title-cell">
                <span class="requirement-title-icon"><SvgIcon icon="mdi:clipboard-check-outline" /></span>
                <span class="requirement-title-copy">
                  <strong>{{ row.title }}</strong>
                  <small>{{ row.caseCode }} · V{{ row.version }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="类型" width="110">
            <template #default="{ row }">{{ caseTypeLabel(row.caseType) }}</template>
          </ElTableColumn>
          <ElTableColumn prop="moduleName" label="模块" min-width="130">
            <template #default="{ row }">{{ row.moduleName || '-' }}</template>
          </ElTableColumn>
          <ElTableColumn prop="priority" label="优先级" width="82" align="center" />
          <ElTableColumn label="来源" width="78" align="center">
            <template #default="{ row }">
              {{ row.source === 'AI_GENERATED' ? 'AI' : row.source === 'MANUAL' ? '人工' : '导入' }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="100" align="center">
            <template #default="{ row }">
              <ElTag :type="statusType(row.status)">{{ statusLabel(row.status) }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="自动化" width="86" align="center">
            <template #default="{ row }">
              <span class="automation-indicator">
                <SvgIcon :icon="row.automatable ? 'mdi:check-circle-outline' : 'mdi:minus-circle-outline'" />
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" width="150">
            <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="270" fixed="right" align="center">
            <template #default="{ row }: { row: Api.RequirementManage.TestCase }">
              <ElButton
                v-if="!['PUBLISHED', 'DISABLED'].includes(row.status)"
                text
                circle
                title="编辑"
                @click="openDrawer(row)"
              >
                <SvgIcon icon="mdi:pencil-outline" />
              </ElButton>
              <ElButton
                v-if="canReview && ['DRAFT', 'REVIEWING', 'REJECTED'].includes(row.status)"
                text
                type="success"
                title="接受"
                @click="changeCaseStatus(row, 'ACCEPT')"
              >
                接受
              </ElButton>
              <ElButton
                v-if="canReview && row.status === 'APPROVED'"
                text
                type="primary"
                title="发布"
                @click="changeCaseStatus(row, 'PUBLISH')"
              >
                发布
              </ElButton>
              <ElButton
                v-if="canReview && row.status === 'PUBLISHED'"
                text
                type="warning"
                title="停用"
                @click="changeCaseStatus(row, 'DISABLE')"
              >
                停用
              </ElButton>
              <ElButton
                v-if="canManage && ['PUBLISHED', 'DISABLED'].includes(row.status)"
                text
                type="primary"
                title="复制为可编辑的接口自动化草稿"
                @click="cloneAsAutomationDraft(row)"
              >
                <SvgIcon icon="mdi:content-copy" />
                创建自动化版本
              </ElButton>
              <ElButton v-if="canManage" text circle type="danger" @click="deleteCase(row)">
                <SvgIcon icon="mdi:delete-outline" />
              </ElButton>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前项目暂无测试用例" :image-size="72" /></template>
        </ElTable>
      </div>

      <div v-else v-loading="loading" class="requirement-mobile-list">
        <article
          v-for="row in records"
          :key="row.id"
          class="requirement-mobile-card"
          @click="!['PUBLISHED', 'DISABLED'].includes(row.status) && openDrawer(row)"
        >
          <div class="requirement-mobile-head">
            <strong>{{ row.caseCode }}</strong>
            <ElTag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</ElTag>
          </div>
          <h3>{{ row.title }}</h3>
          <p>{{ caseTypeLabel(row.caseType) }} · {{ row.priority }} · {{ row.moduleName || '未关联模块' }}</p>
          <div class="requirement-mobile-foot">
            <span>{{ row.steps.length }} 个步骤</span>
            <span>{{ row.source === 'AI_GENERATED' ? 'AI 生成' : '人工用例' }}</span>
            <ElButton
              v-if="canManage && ['PUBLISHED', 'DISABLED'].includes(row.status)"
              text
              type="primary"
              @click.stop="cloneAsAutomationDraft(row)"
            >
              创建自动化版本
            </ElButton>
          </div>
        </article>
        <ElEmpty v-if="!records.length && !loading" description="当前项目暂无测试用例" :image-size="72" />
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

    <ElDrawer
      v-model="drawerVisible"
      :title="automationRevisionSourceId ? '修正并创建接口自动化版本' : editingId ? '编辑测试用例' : '新建测试用例'"
      :size="isMobile ? '100%' : '760px'"
      destroy-on-close
    >
      <div v-loading="detailLoading">
        <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
          <div class="case-form-grid">
            <ElFormItem label="用例编码" prop="caseCode"><ElInput v-model="form.caseCode" maxlength="80" /></ElFormItem>
            <ElFormItem label="所属模块">
              <ElSelect v-model="form.moduleId" clearable filterable>
                <ElOption v-for="item in modules" :key="item.id" :label="item.name" :value="item.id" />
              </ElSelect>
            </ElFormItem>
          </div>
          <ElFormItem label="用例标题" prop="title">
            <ElInput v-model="form.title" maxlength="300" show-word-limit />
          </ElFormItem>
          <div class="case-form-grid is-three">
            <ElFormItem label="测试类型" prop="caseType">
              <ElSelect v-model="form.caseType">
                <ElOption
                  v-for="item in testCaseTypeOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="优先级" prop="priority">
              <ElSelect v-model="form.priority">
                <ElOption v-for="item in priorityOptions" :key="item.value" :label="item.label" :value="item.value" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="版本">
              <ElInputNumber v-model="form.version" :min="1" controls-position="right" />
            </ElFormItem>
          </div>
          <ElFormItem label="前置条件"><ElInput v-model="form.preconditions" type="textarea" :rows="3" /></ElFormItem>
          <ElFormItem label="总体预期"><ElInput v-model="form.expectedSummary" type="textarea" :rows="3" /></ElFormItem>
          <ElAlert
            v-if="form.caseType === 'API' && form.automatable"
            class="automation-form-help"
            type="info"
            :closable="false"
            title="接口自动化步骤需要 request（如何请求）和 assertions（如何判断成功）"
            description="直接在步骤表单中选择请求方式、填写接口路径并添加结果断言；页面会自动生成后端需要的 JSON。发布时后端会再次完整校验。"
            show-icon
          />
          <ElAlert
            v-else-if="form.automatable"
            class="automation-form-help"
            type="warning"
            :closable="false"
            title="当前自动化执行器只支持接口测试"
            description="请把测试类型改为“接口测试”，或者关闭“适合自动化”。"
            show-icon
          />
          <ElFormItem label="关联已确认需求点">
            <ElSelect
              v-model="form.requirementItemIds"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              clearable
              placeholder="可选；用于覆盖矩阵和需求追溯"
            >
              <ElOption
                v-for="item in requirementItemOptions"
                :key="item.id"
                :label="`${item.requirementTitle} / ${item.itemCode || `#${item.id}`} ${item.title}`"
                :value="item.id"
              />
            </ElSelect>
          </ElFormItem>
          <div class="step-header">
            <strong>测试步骤</strong>
            <ElButton text type="primary" @click="addStep">
              <SvgIcon icon="mdi:plus" />
              添加步骤
            </ElButton>
          </div>
          <div
            v-for="(step, index) in form.steps"
            :key="index"
            class="step-card"
            :class="{ 'is-automation': form.caseType === 'API' && form.automatable }"
          >
            <div class="step-number">
              <span>{{ index + 1 }}</span>
              <ElButton
                class="step-delete-button"
                text
                circle
                type="danger"
                title="删除步骤"
                @click.stop="removeStep(index)"
              >
                <SvgIcon icon="mdi:close" />
              </ElButton>
            </div>
            <ElInput
              v-model="step.action"
              class="step-action"
              type="textarea"
              :rows="2"
              placeholder="操作步骤（必填）"
            />
            <AutomationStepEditor
              v-if="form.caseType === 'API' && form.automatable"
              v-model="step.testData"
              class="step-automation-editor"
            />
            <ElInput v-else v-model="step.testData" type="textarea" :rows="2" placeholder="测试数据（可选）" />
            <ElInput
              v-model="step.expectedResult"
              class="step-expected-result"
              type="textarea"
              :rows="2"
              placeholder="预期结果（必填）"
            />
          </div>
          <ElFormItem label="适合自动化">
            <ElSwitch v-model="form.automatable" />
            <span class="automation-switch-help">开启后，发布前必须补齐每一步的接口请求和结果断言。</span>
          </ElFormItem>
        </ElForm>
      </div>
      <template #footer>
        <ElButton @click="drawerVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitCase">保存用例</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.automation-indicator {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.automation-form-help {
  margin-bottom: 16px;
}
.automation-switch-help {
  margin-left: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.case-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.case-form-grid.is-three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.step-header,
.step-number {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.step-card {
  display: grid;
  grid-template-columns: 42px repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px;
}
.step-card > * {
  min-width: 0;
}
.step-card.is-automation {
  grid-template-columns: 42px repeat(2, minmax(0, 1fr));
}
.step-card.is-automation .step-number {
  grid-row: 1 / span 2;
}
.step-card.is-automation .step-action {
  grid-row: 1;
  grid-column: 2;
}
.step-card.is-automation .step-expected-result {
  grid-row: 1;
  grid-column: 3;
}
.step-card.is-automation .step-automation-editor {
  grid-row: 2;
  grid-column: 2 / -1;
}
.step-number {
  align-self: start;
  flex-direction: column;
  color: rgb(var(--primary-color));
  font-weight: 700;
}
.step-delete-button {
  position: relative;
  z-index: 2;
  width: 32px;
  height: 32px;
  padding: 0;
}
@media (max-width: 700px) {
  .case-form-grid,
  .case-form-grid.is-three,
  .step-card {
    grid-template-columns: 1fr;
  }
  .step-card.is-automation {
    grid-template-columns: 1fr;
  }
  .step-card.is-automation .step-number,
  .step-card.is-automation .step-action,
  .step-card.is-automation .step-expected-result,
  .step-card.is-automation .step-automation-editor {
    grid-row: auto;
    grid-column: auto;
  }
  .step-number {
    flex-direction: row;
  }
}
</style>
