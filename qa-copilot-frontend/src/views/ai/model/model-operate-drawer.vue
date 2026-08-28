<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchCreateAIModel, fetchGetAIProviderList, fetchUpdateAIModel } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'ModelOperateDrawer' });

interface Props {
  operateType: UI.TableOperateType;
  rowData?: Api.AIManage.Model | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'submitted'): void }>();
const visible = defineModel<boolean>('visible', { default: false });

type FormModel = {
  providerId: number | null;
  name: string;
  modelId: string;
  reasoningEffort: string | null;
  contextWindowTokens: number;
  maxOutputTokens: number;
  enabled: boolean;
  isDefault: boolean;
  taskTypes: string[];
};

const { formRef, validate, restoreValidation } = useForm();
const { defaultRequiredRule } = useFormRules();
const submitting = ref(false);
const providerLoading = ref(false);
const providers = ref<Api.AIManage.Provider[]>([]);
const model = ref(createDefaultModel());

const title = computed(() => $t(props.operateType === 'add' ? 'page.ai.model.addModel' : 'page.ai.model.editModel'));

const rules = {
  providerId: defaultRequiredRule,
  name: defaultRequiredRule,
  modelId: defaultRequiredRule
};

function createDefaultModel(): FormModel {
  return {
    providerId: null,
    name: '',
    modelId: '',
    reasoningEffort: null,
    contextWindowTokens: 32768,
    maxOutputTokens: 4096,
    enabled: true,
    isDefault: false,
    taskTypes: []
  };
}

function initModel() {
  model.value = createDefaultModel();

  if (props.operateType === 'edit' && props.rowData) {
    model.value = {
      providerId: props.rowData.providerId,
      name: props.rowData.name,
      modelId: props.rowData.modelId,
      reasoningEffort: props.rowData.reasoningEffort,
      contextWindowTokens: props.rowData.contextWindowTokens,
      maxOutputTokens: props.rowData.maxOutputTokens,
      enabled: props.rowData.enabled,
      isDefault: props.rowData.isDefault,
      taskTypes: [...props.rowData.taskTypes]
    };
  }
}

async function getProviders() {
  providerLoading.value = true;
  const { data, error } = await fetchGetAIProviderList();
  providerLoading.value = false;
  if (!error) providers.value = data;
}

function closeDrawer() {
  visible.value = false;
}

async function handleSubmit() {
  await validate();
  const form = model.value;
  if (form.maxOutputTokens >= form.contextWindowTokens) {
    window.$message?.error($t('page.ai.model.tokenLimitInvalid'));
    return;
  }

  submitting.value = true;
  const commonParams = {
    name: form.name.trim(),
    modelId: form.modelId.trim(),
    reasoningEffort: form.reasoningEffort || null,
    contextWindowTokens: form.contextWindowTokens,
    maxOutputTokens: form.maxOutputTokens,
    enabled: form.enabled,
    isDefault: form.isDefault,
    taskTypes: form.taskTypes.map(item => item.trim()).filter(Boolean)
  };
  const { error } =
    props.operateType === 'add'
      ? await fetchCreateAIModel({
          ...commonParams,
          providerId: form.providerId!
        })
      : await fetchUpdateAIModel(props.rowData!.id, commonParams);

  submitting.value = false;
  if (error) return;

  window.$message?.success($t(props.operateType === 'add' ? 'common.addSuccess' : 'common.updateSuccess'));
  closeDrawer();
  emit('submitted');
}

watch(visible, value => {
  if (value) {
    initModel();
    restoreValidation();
    getProviders();
  }
});
</script>

<template>
  <ElDrawer v-model="visible" :size="520" class="model-operate-drawer">
    <template #header>
      <div class="model-drawer-heading">
        <span class="model-drawer-heading__icon"><icon-material-symbols-neurology-outline-rounded /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>{{ $t('page.ai.model.configDescription') }}</small>
        </div>
      </div>
    </template>

    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="model-form">
      <section class="model-form-section">
        <h3>{{ $t('page.manage.common.basicInfo') }}</h3>
        <ElFormItem :label="$t('page.ai.model.provider')" prop="providerId">
          <ElSelect
            v-model="model.providerId"
            :loading="providerLoading"
            :disabled="props.operateType === 'edit'"
            class="w-full"
            :placeholder="$t('page.ai.model.form.provider')"
          >
            <ElOption
              v-for="provider in providers"
              :key="provider.id"
              :label="provider.name"
              :value="provider.id"
              :disabled="!provider.enabled"
            />
          </ElSelect>
          <p v-if="props.operateType === 'edit'" class="model-form-hint">
            {{ $t('page.ai.model.providerLocked') }}
          </p>
        </ElFormItem>
        <ElFormItem :label="$t('page.ai.model.name')" prop="name">
          <ElInput v-model="model.name" :placeholder="$t('page.ai.model.form.name')" maxlength="100" />
        </ElFormItem>
        <ElFormItem :label="$t('page.ai.model.modelId')" prop="modelId">
          <ElInput v-model="model.modelId" :placeholder="$t('page.ai.model.form.modelId')" maxlength="160" />
        </ElFormItem>
      </section>

      <section class="model-form-section">
        <h3>{{ $t('page.ai.model.runtimeConfig') }}</h3>
        <div class="model-form-grid">
          <ElFormItem :label="$t('page.ai.model.reasoningEffort')" prop="reasoningEffort">
            <ElSelect
              v-model="model.reasoningEffort"
              clearable
              filterable
              allow-create
              default-first-option
              class="w-full"
              :placeholder="$t('page.ai.model.form.reasoningEffort')"
            >
              <ElOption :label="$t('page.ai.model.reasoningEffortOptions.minimal')" value="minimal" />
              <ElOption :label="$t('page.ai.model.reasoningEffortOptions.low')" value="low" />
              <ElOption :label="$t('page.ai.model.reasoningEffortOptions.medium')" value="medium" />
              <ElOption :label="$t('page.ai.model.reasoningEffortOptions.high')" value="high" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem :label="$t('page.ai.model.contextWindowTokens')" prop="contextWindowTokens">
            <ElInputNumber
              v-model="model.contextWindowTokens"
              :min="1024"
              :max="2000000"
              :step="1024"
              controls-position="right"
              class="w-full"
            />
          </ElFormItem>
          <ElFormItem :label="$t('page.ai.model.maxOutputTokens')" prop="maxOutputTokens">
            <ElInputNumber
              v-model="model.maxOutputTokens"
              :min="128"
              :max="128000"
              :step="128"
              controls-position="right"
              class="w-full"
            />
          </ElFormItem>
        </div>
        <ElFormItem :label="$t('page.ai.model.taskTypes')" prop="taskTypes">
          <ElSelect
            v-model="model.taskTypes"
            multiple
            filterable
            allow-create
            default-first-option
            class="w-full"
            :placeholder="$t('page.ai.model.form.taskTypes')"
          >
            <ElOption :label="$t('page.ai.model.taskTypeOptions.testCase')" value="test_case_generation" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.review')" value="test_review" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.defect')" value="defect_analysis" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.qa')" value="knowledge_qa" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.queryRewrite')" value="query_rewrite" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.requirementAnalysis')" value="requirement_analysis" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.coverageAnalysis')" value="coverage_analysis" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.supervisorPlanning')" value="supervisor_planning" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.embedding')" value="embedding" />
            <ElOption :label="$t('page.ai.model.taskTypeOptions.rerank')" value="rerank" />
          </ElSelect>
        </ElFormItem>
        <div class="model-switch-list">
          <div class="model-switch-row">
            <div>
              <strong>{{ $t('page.manage.user.userStatus') }}</strong>
              <small>{{ $t('page.ai.model.statusDescription') }}</small>
            </div>
            <ElSwitch v-model="model.enabled" />
          </div>
          <div class="model-switch-row">
            <div>
              <strong>{{ $t('page.ai.model.defaultModel') }}</strong>
              <small>{{ $t('page.ai.model.defaultDescription') }}</small>
            </div>
            <ElSwitch v-model="model.isDefault" />
          </div>
        </div>
      </section>
    </ElForm>

    <template #footer>
      <ElButton @click="closeDrawer">{{ $t('common.cancel') }}</ElButton>
      <ElButton type="primary" :loading="submitting" @click="handleSubmit">{{ $t('common.confirm') }}</ElButton>
    </template>
  </ElDrawer>
</template>

<style lang="scss">
.model-operate-drawer .el-drawer__header {
  margin-bottom: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 18px 20px;
}

.model-operate-drawer .el-drawer__body {
  padding: 0;
}

.model-operate-drawer .el-drawer__footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 20px;
}

.model-drawer-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.model-drawer-heading__icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 18px;
}

.model-drawer-heading strong,
.model-drawer-heading small {
  display: block;
}

.model-drawer-heading strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.model-drawer-heading small,
.model-form-hint,
.model-switch-row small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.model-drawer-heading small,
.model-form-hint,
.model-switch-row small {
  margin-top: 3px;
}

.model-form-section {
  padding: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.model-form-section h3 {
  margin: 0 0 18px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 650;
}

.model-form .el-form-item {
  margin-bottom: 18px;
}

.model-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.model-form-hint {
  margin-bottom: 0;
}

.model-switch-list {
  display: grid;
  gap: 10px;
}

.model-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
}

.model-switch-row strong,
.model-switch-row small {
  display: block;
}

.model-switch-row strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 550;
}
</style>
