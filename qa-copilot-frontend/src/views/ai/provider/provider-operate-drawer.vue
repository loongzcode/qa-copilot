<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchCreateAIProvider, fetchUpdateAIProvider } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'ProviderOperateDrawer' });

interface Props {
  operateType: UI.TableOperateType;
  rowData?: Api.AIManage.Provider | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'submitted'): void }>();
const visible = defineModel<boolean>('visible', { default: false });

type FormModel = {
  name: string;
  providerType: Api.AIManage.ProviderType;
  baseUrl: string;
  apiKey: string;
  customHeadersText: string;
  timeoutSeconds: number;
  maxRetries: number;
  enabled: boolean;
};

const { formRef, validate, restoreValidation } = useForm();
const { defaultRequiredRule } = useFormRules();
const submitting = ref(false);
const model = ref(createDefaultModel());

const title = computed(() =>
  $t(props.operateType === 'add' ? 'page.ai.provider.addProvider' : 'page.ai.provider.editProvider')
);

function createDefaultModel(): FormModel {
  return {
    name: '',
    providerType: 'openai_responses',
    baseUrl: '',
    apiKey: '',
    customHeadersText: '{}',
    timeoutSeconds: 120,
    maxRetries: 2,
    enabled: true
  };
}

function validateHeaders(_rule: unknown, value: string, callback: (error?: Error) => void) {
  try {
    const parsed = JSON.parse(value || '{}');
    const valid =
      parsed &&
      !Array.isArray(parsed) &&
      typeof parsed === 'object' &&
      Object.values(parsed).every(item => typeof item === 'string');

    callback(valid ? undefined : new Error($t('page.ai.provider.form.headersInvalid')));
  } catch {
    callback(new Error($t('page.ai.provider.form.headersInvalid')));
  }
}

const rules = {
  name: defaultRequiredRule,
  customHeadersText: { trigger: 'blur', validator: validateHeaders }
};

function initModel() {
  model.value = createDefaultModel();

  if (props.operateType === 'edit' && props.rowData) {
    model.value = {
      name: props.rowData.name,
      providerType: props.rowData.providerType,
      baseUrl: props.rowData.baseUrl || '',
      apiKey: '',
      customHeadersText: JSON.stringify(props.rowData.customHeaders || {}, null, 2),
      timeoutSeconds: props.rowData.timeoutSeconds,
      maxRetries: props.rowData.maxRetries,
      enabled: props.rowData.enabled
    };
  }
}

function closeDrawer() {
  visible.value = false;
}

async function handleSubmit() {
  await validate();
  submitting.value = true;

  const form = model.value;
  const baseParams: Api.AIManage.ProviderCreateParams = {
    name: form.name.trim(),
    providerType: form.providerType,
    baseUrl: form.baseUrl.trim() || null,
    apiKey: form.apiKey,
    customHeaders: JSON.parse(form.customHeadersText || '{}'),
    timeoutSeconds: form.timeoutSeconds,
    maxRetries: form.maxRetries,
    enabled: form.enabled
  };
  const { error } =
    props.operateType === 'add'
      ? await fetchCreateAIProvider(baseParams)
      : await fetchUpdateAIProvider(props.rowData!.id, {
          ...baseParams,
          apiKey: form.apiKey || undefined
        });

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
  }
});
</script>

<template>
  <ElDrawer v-model="visible" :size="520" class="provider-operate-drawer">
    <template #header>
      <div class="provider-drawer-heading">
        <span class="provider-drawer-heading__icon"><icon-material-symbols-lan-outline-rounded /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>{{ $t('page.ai.provider.configDescription') }}</small>
        </div>
      </div>
    </template>

    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="provider-form">
      <section class="provider-form-section">
        <h3>{{ $t('page.manage.common.basicInfo') }}</h3>
        <ElFormItem :label="$t('page.ai.provider.name')" prop="name">
          <ElInput v-model="model.name" :placeholder="$t('page.ai.provider.form.name')" maxlength="100" />
        </ElFormItem>
        <ElFormItem :label="$t('page.ai.provider.providerType')" prop="providerType">
          <ElSelect v-model="model.providerType" class="w-full">
            <ElOption :label="$t('page.ai.provider.type.responses')" value="openai_responses" />
            <ElOption :label="$t('page.ai.provider.type.compatible')" value="openai_compatible" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem :label="$t('page.ai.provider.baseUrl')" prop="baseUrl">
          <ElInput v-model="model.baseUrl" :placeholder="$t('page.ai.provider.form.baseUrl')" maxlength="500" />
        </ElFormItem>
        <ElFormItem :label="$t('page.ai.provider.apiKey')" prop="apiKey">
          <ElInput
            v-model="model.apiKey"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
            :placeholder="
              $t(props.operateType === 'edit' ? 'page.ai.provider.form.apiKeyEdit' : 'page.ai.provider.form.apiKey')
            "
            maxlength="500"
          />
          <p v-if="props.operateType === 'edit' && props.rowData?.apiKeyMasked" class="provider-form-hint">
            {{ $t('page.ai.provider.currentKey') }}：{{ props.rowData.apiKeyMasked }}
          </p>
        </ElFormItem>
      </section>

      <section class="provider-form-section">
        <h3>{{ $t('page.ai.provider.requestConfig') }}</h3>
        <div class="provider-form-grid">
          <ElFormItem :label="$t('page.ai.provider.timeoutSeconds')" prop="timeoutSeconds">
            <ElInputNumber
              v-model="model.timeoutSeconds"
              :min="5"
              :max="600"
              controls-position="right"
              class="w-full"
            />
          </ElFormItem>
          <ElFormItem :label="$t('page.ai.provider.maxRetries')" prop="maxRetries">
            <ElInputNumber v-model="model.maxRetries" :min="0" :max="10" controls-position="right" class="w-full" />
          </ElFormItem>
        </div>
        <ElFormItem :label="$t('page.ai.provider.customHeaders')" prop="customHeadersText">
          <ElInput
            v-model="model.customHeadersText"
            type="textarea"
            :rows="5"
            resize="none"
            :placeholder="$t('page.ai.provider.form.customHeaders')"
            class="provider-json-input"
          />
        </ElFormItem>
        <div class="provider-status-row">
          <div>
            <strong>{{ $t('page.manage.user.userStatus') }}</strong>
            <small>{{ $t('page.ai.provider.statusDescription') }}</small>
          </div>
          <ElSwitch v-model="model.enabled" />
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
.provider-operate-drawer .el-drawer__header {
  margin-bottom: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 18px 20px;
}

.provider-operate-drawer .el-drawer__body {
  padding: 0;
}

.provider-operate-drawer .el-drawer__footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 20px;
}

.provider-drawer-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.provider-drawer-heading__icon {
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

.provider-drawer-heading strong,
.provider-drawer-heading small {
  display: block;
}

.provider-drawer-heading strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.provider-drawer-heading small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.provider-form-section {
  padding: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.provider-form-section h3 {
  margin: 0 0 18px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 650;
}

.provider-form .el-form-item {
  margin-bottom: 18px;
}

.provider-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.provider-form-hint {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.4;
}

.provider-json-input textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.provider-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
}

.provider-status-row strong,
.provider-status-row small {
  display: block;
}

.provider-status-row strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 550;
}

.provider-status-row small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
