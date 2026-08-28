<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMediaQuery } from '@vueuse/core';
import type { FormInstance, FormRules } from 'element-plus';
import {
  fetchConfirmRequirementItems,
  fetchCreateRequirementItem,
  fetchDeleteRequirementItem,
  fetchExtractRequirement,
  fetchGetLatestRequirementExtractionTask,
  fetchGetQualityDeliveryStatus,
  fetchGetRequirementDetail,
  fetchGetRequirementExtractionTask,
  fetchUpdateRequirementItem
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import {
  priorityOptions,
  requirementItemTypeLabel,
  requirementItemTypeOptions,
  requirementStatusLabel,
  requirementStatusType
} from '../shared';

defineOptions({ name: 'RequirementDetail' });

type ItemForm = Omit<Api.RequirementManage.RequirementItemCreateParams, 'itemCode'> & { itemCode: string };

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 700px)');
const loading = ref(false);
const submitting = ref(false);
const detail = ref<Api.RequirementManage.RequirementDetail | null>(null);
const qualityDelivery = ref<Api.RequirementManage.QualityDeliveryStatus | null>(null);
const selectedItems = ref<Api.RequirementManage.RequirementItem[]>([]);
const drawerVisible = ref(false);
const editingItemId = ref<number | null>(null);
const formRef = ref<FormInstance>();
const extractionTask = ref<Api.RequirementManage.RequirementExtractionTask | null>(null);
let extractionPollTimer: ReturnType<typeof setTimeout> | null = null;
let resumingExtraction = false;

const projectId = computed(() => Number(route.query.projectId) || 0);
const requirementId = computed(() => Number(route.query.requirementId) || 0);
const canManage = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('requirement:manage');
});
const canExtract = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('requirement:extract');
});
const unconfirmedSelectedIds = computed(() => selectedItems.value.filter(item => !item.confirmed).map(item => item.id));
const extractionRunning = computed(
  () => extractionTask.value?.status === 'PENDING' || extractionTask.value?.status === 'RUNNING'
);

const extractionStageLabel: Record<Api.RequirementManage.RequirementExtractionStage, string> = {
  QUEUED: '等待 Worker 领取',
  LOADING_DOCUMENT: '读取需求文档',
  CALLING_MODEL: 'AI 正在拆解需求',
  VALIDATING_OUTPUT: '校验模型输出',
  SAVING_ITEMS: '保存原子需求点',
  FINISHED: '处理完成'
};

const qualityStageLabel: Record<Api.RequirementManage.QualityDeliveryStage, string> = {
  START_REQUIREMENT_AGENT: '等待需求拆解',
  REQUIREMENT_AGENT_RUNNING: '需求拆解中',
  REQUIREMENT_AGENT_FAILED: '需求拆解失败',
  HUMAN_REQUIREMENT_REVIEW: '等待人工确认需求点',
  START_CASE_AGENT: '等待覆盖分析与用例生成',
  CASE_AGENT_RUNNING: '测试用例生成中',
  CASE_AGENT_FAILED: '测试用例生成失败',
  HUMAN_CASE_REVIEW: '等待人工审核用例',
  IMPROVE_AUTOMATION_DATA: '等待补齐自动化数据',
  READY_FOR_AUTOMATION: '可以进入自动化执行'
};

const qualityStageType = computed(() => {
  if (!qualityDelivery.value) return 'info';
  if (qualityDelivery.value.stage === 'READY_FOR_AUTOMATION') return 'success';
  if (['REQUIREMENT_AGENT_FAILED', 'CASE_AGENT_FAILED'].includes(qualityDelivery.value.stage)) return 'error';
  if (qualityDelivery.value.blockers.length) return 'warning';
  return 'info';
});

const form = reactive<ItemForm>({
  parentId: null,
  itemCode: '',
  title: '',
  description: '',
  itemType: 'FUNCTIONAL',
  priority: 'P2',
  acceptanceCriteria: '',
  sourceLocator: {}
});

const rules: FormRules<ItemForm> = {
  itemCode: [{ required: true, message: '请输入需求点编码', trigger: 'blur' }],
  title: [{ required: true, message: '请输入需求点标题', trigger: 'blur' }],
  description: [{ required: true, message: '请输入需求点说明', trigger: 'blur' }],
  itemType: [{ required: true, message: '请选择需求点类型', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }]
};

async function getDetail() {
  if (!projectId.value || !requirementId.value) return;
  loading.value = true;
  const [detailResult, deliveryResult] = await Promise.all([
    fetchGetRequirementDetail(projectId.value, requirementId.value),
    fetchGetQualityDeliveryStatus(projectId.value, requirementId.value)
  ]);
  loading.value = false;
  if (!detailResult.error) {
    detail.value = detailResult.data;
    if (detailResult.data.status === 'EXTRACTING') void resumeExtractionPolling();
  }
  if (!deliveryResult.error) qualityDelivery.value = deliveryResult.data;
}

function stopExtractionPolling() {
  if (extractionPollTimer) clearTimeout(extractionPollTimer);
  extractionPollTimer = null;
}

/** 按准确 taskId 轮询，结束后刷新需求点树并展示最终结果。 */
async function pollExtractionTask(taskId: number) {
  const { data, error } = await fetchGetRequirementExtractionTask(projectId.value, requirementId.value, taskId);
  if (error) {
    stopExtractionPolling();
    return;
  }
  extractionTask.value = data;
  if (data.status === 'PENDING' || data.status === 'RUNNING') {
    extractionPollTimer = setTimeout(() => {
      void pollExtractionTask(taskId);
    }, 1500);
    return;
  }

  stopExtractionPolling();
  if (data.status === 'COMPLETED') {
    window.$message?.success('需求拆解完成，请校正并确认生成的需求点');
  } else {
    window.$message?.error(data.errorMessage || '需求拆解失败');
  }
  await getDetail();
}

/** 页面刷新后根据最近活动任务恢复进度，而不是重新提交拆解。 */
async function resumeExtractionPolling() {
  if (extractionRunning.value || resumingExtraction) return;
  resumingExtraction = true;
  const { data, error } = await fetchGetLatestRequirementExtractionTask(projectId.value, requirementId.value);
  resumingExtraction = false;
  if (error || !data || (data.status !== 'PENDING' && data.status !== 'RUNNING')) return;
  extractionTask.value = data;
  await pollExtractionTask(data.id);
}

function resetForm() {
  Object.assign(form, {
    parentId: null,
    itemCode: '',
    title: '',
    description: '',
    itemType: 'FUNCTIONAL',
    priority: 'P2',
    acceptanceCriteria: '',
    sourceLocator: {}
  });
}

async function openItemDrawer(item?: Api.RequirementManage.RequirementItem) {
  editingItemId.value = item?.id ?? null;
  if (item) {
    Object.assign(form, {
      parentId: item.parentId,
      itemCode: item.itemCode || '',
      title: item.title,
      description: item.description,
      itemType: item.itemType,
      priority: item.priority,
      acceptanceCriteria: item.acceptanceCriteria,
      sourceLocator: item.sourceLocator
    });
  } else {
    resetForm();
  }
  drawerVisible.value = true;
  await nextTick();
  formRef.value?.clearValidate();
}

async function submitItem() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !projectId.value || !requirementId.value) return;
  const payload: ItemForm = {
    ...form,
    itemCode: form.itemCode.trim(),
    title: form.title.trim(),
    description: form.description.trim(),
    acceptanceCriteria: form.acceptanceCriteria.trim()
  };

  submitting.value = true;
  const result = editingItemId.value
    ? await fetchUpdateRequirementItem(projectId.value, requirementId.value, editingItemId.value, payload)
    : await fetchCreateRequirementItem(projectId.value, requirementId.value, payload);
  submitting.value = false;
  if (result.error) return;
  drawerVisible.value = false;
  window.$message?.success(editingItemId.value ? '需求点已更新' : '需求点已添加');
  await getDetail();
}

async function deleteItem(item: Api.RequirementManage.RequirementItem) {
  await ElMessageBox.confirm(`确认删除需求点“${item.itemCode} ${item.title}”吗？`, '删除需求点', { type: 'warning' });
  const { error } = await fetchDeleteRequirementItem(projectId.value, requirementId.value, item.id);
  if (error) return;
  window.$message?.success('需求点已删除');
  await getDetail();
}

async function confirmSelected() {
  if (!unconfirmedSelectedIds.value.length) {
    window.$message?.warning('请先选择尚未确认的需求点');
    return;
  }
  const { error } = await fetchConfirmRequirementItems(
    projectId.value,
    requirementId.value,
    unconfirmedSelectedIds.value
  );
  if (error) return;
  selectedItems.value = [];
  window.$message?.success('所选需求点已确认');
  await getDetail();
}

async function extractAgain() {
  const { data, error } = await fetchExtractRequirement(projectId.value, requirementId.value);
  if (error) return;
  stopExtractionPolling();
  extractionTask.value = data;
  window.$message?.success('需求拆解任务已重新提交');
  await getDetail();
  await pollExtractionTask(data.id);
}

function openCoverage() {
  void router.push({
    path: '/requirement/coverage',
    query: { projectId: projectId.value, requirementId: requirementId.value }
  });
}

void getDetail();
onBeforeUnmount(stopExtractionPolling);
</script>

<template>
  <div class="requirement-page requirement-detail-page">
    <ElCard v-loading="loading" class="requirement-card">
      <template #header>
        <div class="requirement-header">
          <div class="requirement-heading detail-heading">
            <ElButton text circle title="返回需求列表" @click="router.back()">
              <SvgIcon icon="mdi:arrow-left" />
            </ElButton>
            <div>
              <h2>{{ detail?.title || '需求详情' }}</h2>
              <p v-if="detail">
                V{{ detail.version }} · {{ detail.moduleName || '全部模块' }} ·
                {{ detail.documentTitle || '未关联原始文档' }}
              </p>
            </div>
          </div>
          <div class="requirement-header-actions">
            <ElTag v-if="detail" :type="requirementStatusType(detail.status)">
              {{ requirementStatusLabel(detail.status) }}
            </ElTag>
            <ElButton
              v-if="canExtract"
              :loading="extractionRunning"
              :disabled="extractionRunning"
              @click="extractAgain"
            >
              <SvgIcon icon="mdi:creation-outline" />
              重新拆解
            </ElButton>
            <ElButton type="primary" :disabled="detail?.status !== 'CONFIRMED'" @click="openCoverage">
              进入覆盖分析
            </ElButton>
          </div>
        </div>
      </template>

      <template v-if="detail">
        <section v-if="qualityDelivery" class="quality-delivery-status">
          <ElAlert
            :type="qualityStageType"
            :title="qualityStageLabel[qualityDelivery.stage]"
            :description="qualityDelivery.nextAction"
            :closable="false"
            show-icon
          />
          <div class="quality-delivery-facts">
            <span>
              需求点 {{ qualityDelivery.confirmedItemCount }}/{{ qualityDelivery.requirementItemCount }} 已确认
            </span>
            <span>{{ qualityDelivery.reviewCaseCount }} 条用例待审核</span>
            <span>{{ qualityDelivery.publishedCaseCount }} 条已发布</span>
            <span>{{ qualityDelivery.automatablePublishedCaseCount }} 条自动化就绪</span>
          </div>
        </section>

        <section v-if="extractionRunning && extractionTask" class="extraction-progress">
          <div>
            <strong>{{ extractionStageLabel[extractionTask.currentStage] }}</strong>
            <span>{{ extractionTask.progress }}%</span>
          </div>
          <ElProgress :percentage="extractionTask.progress" :stroke-width="8" :show-text="false" />
        </section>

        <section class="detail-summary">
          <div>
            <span>需求点总数</span>
            <strong>{{ detail.itemCount }}</strong>
          </div>
          <div>
            <span>已人工确认</span>
            <strong>{{ detail.confirmedItemCount }}</strong>
          </div>
          <div>
            <span>待确认</span>
            <strong>{{ detail.itemCount - detail.confirmedItemCount }}</strong>
          </div>
          <div>
            <span>创建人</span>
            <strong class="is-text">{{ detail.createdByName || '-' }}</strong>
          </div>
        </section>

        <div class="requirement-toolbar detail-toolbar">
          <div>
            <strong>原子需求点</strong>
            <span class="requirement-muted">AI 拆解结果必须人工校正和确认</span>
          </div>
          <div class="requirement-inline-actions">
            <ElButton v-if="canManage" :disabled="!unconfirmedSelectedIds.length" @click="confirmSelected">
              确认所选（{{ unconfirmedSelectedIds.length }}）
            </ElButton>
            <ElButton v-if="canManage" type="primary" @click="openItemDrawer()">
              <SvgIcon icon="mdi:plus" />
              添加需求点
            </ElButton>
          </div>
        </div>

        <div v-if="!isMobile" class="detail-table-wrap">
          <ElTable :data="detail.items" border row-key="id" @selection-change="selectedItems = $event">
            <ElTableColumn type="selection" width="48" />
            <ElTableColumn prop="itemCode" label="编码" width="112" />
            <ElTableColumn label="需求点" min-width="300">
              <template #default="{ row }: { row: Api.RequirementManage.RequirementItem }">
                <div class="item-title">
                  <strong>{{ row.title }}</strong>
                  <small>{{ row.description }}</small>
                </div>
              </template>
            </ElTableColumn>
            <ElTableColumn label="类型" width="116">
              <template #default="{ row }">{{ requirementItemTypeLabel(row.itemType) }}</template>
            </ElTableColumn>
            <ElTableColumn prop="priority" label="优先级" width="82" align="center" />
            <ElTableColumn label="来源" width="82" align="center">
              <template #default="{ row }">{{ row.aiGenerated ? 'AI' : '人工' }}</template>
            </ElTableColumn>
            <ElTableColumn label="确认" width="88" align="center">
              <template #default="{ row }">
                <ElTag :type="row.confirmed ? 'success' : 'warning'" size="small">
                  {{ row.confirmed ? '已确认' : '待确认' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="102" align="center">
              <template #default="{ row }: { row: Api.RequirementManage.RequirementItem }">
                <ElButton v-if="canManage" text circle @click="openItemDrawer(row)">
                  <SvgIcon icon="mdi:pencil-outline" />
                </ElButton>
                <ElButton v-if="canManage" text circle type="danger" @click="deleteItem(row)">
                  <SvgIcon icon="mdi:delete-outline" />
                </ElButton>
              </template>
            </ElTableColumn>
            <template #empty><ElEmpty description="尚未拆解出原子需求点" :image-size="72" /></template>
          </ElTable>
        </div>

        <div v-else class="requirement-mobile-list">
          <article v-for="item in detail.items" :key="item.id" class="requirement-mobile-card">
            <div class="requirement-mobile-head">
              <strong>{{ item.itemCode }}</strong>
              <ElTag :type="item.confirmed ? 'success' : 'warning'" size="small">
                {{ item.confirmed ? '已确认' : '待确认' }}
              </ElTag>
            </div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.description }}</p>
            <div class="requirement-mobile-foot">
              <span>{{ requirementItemTypeLabel(item.itemType) }} · {{ item.priority }}</span>
              <ElButton v-if="canManage" text size="small" @click="openItemDrawer(item)">编辑</ElButton>
            </div>
          </article>
        </div>
      </template>

      <ElEmpty v-else-if="!loading" description="未找到需求或当前用户无权访问" />
    </ElCard>

    <ElDrawer
      v-model="drawerVisible"
      :title="editingItemId ? '编辑原子需求点' : '添加原子需求点'"
      :size="isMobile ? '100%' : '600px'"
      destroy-on-close
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="item-form-grid">
          <ElFormItem label="需求点编码" prop="itemCode">
            <ElInput v-model="form.itemCode" maxlength="80" placeholder="例如 REQ-001" />
          </ElFormItem>
          <ElFormItem label="优先级" prop="priority">
            <ElSelect v-model="form.priority">
              <ElOption v-for="item in priorityOptions" :key="item.value" :label="item.label" :value="item.value" />
            </ElSelect>
          </ElFormItem>
        </div>
        <ElFormItem label="需求点标题" prop="title">
          <ElInput v-model="form.title" maxlength="300" show-word-limit />
        </ElFormItem>
        <ElFormItem label="需求点类型" prop="itemType">
          <ElSelect v-model="form.itemType">
            <ElOption
              v-for="item in requirementItemTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="详细说明" prop="description">
          <ElInput v-model="form.description" type="textarea" :rows="5" maxlength="10000" show-word-limit />
        </ElFormItem>
        <ElFormItem label="验收条件">
          <ElInput v-model="form.acceptanceCriteria" type="textarea" :rows="4" maxlength="10000" show-word-limit />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="drawerVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitItem">保存需求点</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.detail-heading,
.detail-toolbar,
.detail-toolbar > div,
.item-title {
  display: flex;
}

.detail-heading {
  align-items: center;
  gap: 8px;
}

.detail-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 16px;
}

.detail-summary > div {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
}

.extraction-progress {
  margin: 16px;
  padding: 12px 16px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}

.quality-delivery-status {
  display: grid;
  gap: 8px;
  margin: 16px;
}

.quality-delivery-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  padding: 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.extraction-progress > div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.detail-summary span,
.detail-summary strong {
  display: block;
}

.detail-summary span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.detail-summary strong {
  margin-top: 5px;
  font-size: 22px;
}

.detail-summary strong.is-text {
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-toolbar {
  justify-content: space-between;
}

.detail-toolbar > div {
  align-items: center;
  gap: 10px;
}

.detail-table-wrap {
  padding: 0 16px 16px;
}

.item-title {
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.item-title small {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 12px;
}

@media (max-width: 700px) {
  .detail-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-toolbar,
  .detail-toolbar > div,
  .item-form-grid {
    align-items: stretch;
    grid-template-columns: 1fr;
  }

  .detail-toolbar,
  .detail-toolbar > div {
    flex-direction: column;
  }
}
</style>
