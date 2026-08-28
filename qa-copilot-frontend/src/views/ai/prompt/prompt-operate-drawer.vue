<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import {
  fetchCreatePromptTemplate,
  fetchGetPromptTemplate,
  fetchPreviewPromptTemplate,
  fetchUpdatePromptTemplate
} from '@/service/api';

defineOptions({ name: 'PromptOperateDrawer' });

interface Props {
  operateType: UI.TableOperateType;
  rowData?: Api.AIManage.PromptTemplateSummary | null;
}

type FormModel = Api.AIManage.PromptTemplateCreateParams;

const props = defineProps<Props>();
const emit = defineEmits<{ (event: 'submitted'): void }>();
const visible = defineModel<boolean>('visible', { default: false });

const REQUIRED_VARIABLES: Record<string, string[]> = {
  rag_answer: ['context', 'question'],
  query_rewrite: ['conversation', 'question'],
  document_summary: ['content']
};

const formRef = ref<FormInstance>();
const loading = ref(false);
const submitting = ref(false);
const previewing = ref(false);
const previewVisible = ref(false);
const previewVariables = reactive<Record<string, string>>({});
const previewResult = ref<Api.AIManage.PromptTemplatePreview | null>(null);
const model = reactive<FormModel>(createDefaultModel());

const title = computed(() => (props.operateType === 'add' ? '新增 Prompt 模板' : '编辑 Prompt 模板'));
const requiredVariables = computed(() => REQUIRED_VARIABLES[model.code] ?? []);
const actualVariables = computed(() => {
  const names = new Set<string>();
  const pattern = /(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})/g;
  for (const text of [model.systemPrompt, model.userPrompt]) {
    for (const match of text.matchAll(pattern)) names.add(match[1]);
  }
  return [...names].sort();
});

const rules: FormRules<FormModel> = {
  code: [
    { required: true, message: '请输入业务编码', trigger: 'blur' },
    {
      pattern: /^[a-z][a-z0-9_]*$/,
      message: '使用小写字母开头，只能包含小写字母、数字和下划线',
      trigger: 'blur'
    }
  ],
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  systemPrompt: [{ validator: validatePromptText, trigger: 'blur' }],
  userPrompt: [{ validator: validatePromptText, trigger: 'blur' }]
};

function createDefaultModel(): FormModel {
  return {
    code: '',
    name: '',
    description: '',
    systemPrompt: '',
    userPrompt: '',
    enabled: true
  };
}

function validatePromptText(_rule: unknown, value: string, callback: (error?: Error) => void) {
  if (!value?.trim()) {
    callback(new Error('Prompt 内容不能为空'));
    return;
  }
  callback();
}

function formatVariable(variable: string) {
  return `{${variable}}`;
}

function resetModel() {
  Object.assign(model, createDefaultModel());
}

async function loadDetail() {
  if (props.operateType !== 'edit' || !props.rowData) return;

  loading.value = true;
  const { data, error } = await fetchGetPromptTemplate(props.rowData.id);
  loading.value = false;

  if (error) {
    visible.value = false;
    return;
  }

  Object.assign(model, {
    code: data.code,
    name: data.name,
    description: data.description,
    systemPrompt: data.systemPrompt,
    userPrompt: data.userPrompt,
    enabled: data.enabled
  });
}

function closeDrawer() {
  visible.value = false;
}

function openPreview() {
  for (const key of Object.keys(previewVariables)) delete previewVariables[key];
  for (const key of actualVariables.value) previewVariables[key] = `【${key} 示例内容】`;
  previewResult.value = null;
  previewVisible.value = true;
}

async function renderPreview() {
  if (!model.code.trim() || !model.systemPrompt.trim() || !model.userPrompt.trim()) {
    return window.$message?.warning('请先补全业务编码和 Prompt 内容');
  }
  previewing.value = true;
  const { data, error } = await fetchPreviewPromptTemplate({
    code: model.code.trim(),
    systemPrompt: model.systemPrompt,
    userPrompt: model.userPrompt,
    variables: { ...previewVariables }
  });
  previewing.value = false;
  if (!error) previewResult.value = data;
}

async function handleSubmit() {
  await formRef.value?.validate();

  submitting.value = true;
  const commonParams = {
    name: model.name.trim(),
    description: model.description.trim(),
    systemPrompt: model.systemPrompt,
    userPrompt: model.userPrompt,
    enabled: model.enabled
  };

  const { error } =
    props.operateType === 'add'
      ? await fetchCreatePromptTemplate({
          ...commonParams,
          code: model.code.trim()
        })
      : await fetchUpdatePromptTemplate(props.rowData!.id, commonParams);

  submitting.value = false;
  if (error) return;

  window.$message?.success(props.operateType === 'add' ? 'Prompt 模板创建成功' : 'Prompt 模板更新成功');
  closeDrawer();
  emit('submitted');
}

watch(visible, async value => {
  if (!value) return;

  resetModel();
  await nextTick();
  formRef.value?.clearValidate();
  await loadDetail();
  await nextTick();
  formRef.value?.clearValidate();
});
</script>

<template>
  <ElDrawer v-model="visible" :size="760" class="prompt-operate-drawer" destroy-on-close>
    <template #header>
      <div class="prompt-drawer-heading">
        <span class="prompt-drawer-heading__icon"><icon-material-symbols-edit-note-rounded /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>配置 AI 工作流实际调用的系统指令与用户消息模板</small>
        </div>
      </div>
    </template>

    <div v-loading="loading" class="prompt-drawer-body">
      <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="prompt-form">
        <section class="prompt-form-section">
          <h3>基本信息</h3>
          <div class="prompt-form-grid">
            <ElFormItem label="模板名称" prop="name">
              <ElInput v-model="model.name" maxlength="100" show-word-limit placeholder="例如：RAG 知识库问答" />
            </ElFormItem>
            <ElFormItem label="业务编码" prop="code">
              <ElInput
                v-model="model.code"
                maxlength="80"
                :disabled="props.operateType === 'edit'"
                placeholder="例如：rag_answer"
              />
              <p class="prompt-form-hint">
                {{
                  props.operateType === 'edit'
                    ? '业务代码依赖该编码，创建后不可修改'
                    : '小写字母开头，可包含数字和下划线'
                }}
              </p>
            </ElFormItem>
          </div>
          <ElFormItem label="用途说明" prop="description">
            <ElInput
              v-model="model.description"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
              placeholder="说明该模板用于哪个 AI 流程"
            />
          </ElFormItem>
          <div class="prompt-switch-row">
            <div>
              <strong>模板状态</strong>
              <small>停用后，依赖该模板的 AI 流程将不能继续调用</small>
            </div>
            <ElSwitch v-model="model.enabled" />
          </div>
        </section>

        <section class="prompt-form-section">
          <div class="prompt-section-heading">
            <div>
              <h3>Prompt 内容</h3>
              <p>
                使用
                <code>{variable_name}</code>
                插入运行时变量；普通花括号请写成双花括号。
              </p>
            </div>
            <div v-if="requiredVariables.length" class="prompt-variable-list">
              <span>必需变量</span>
              <ElTag v-for="variable in requiredVariables" :key="variable" size="small" effect="plain">
                {{ formatVariable(variable) }}
              </ElTag>
            </div>
          </div>

          <ElAlert
            v-if="requiredVariables.length"
            type="info"
            :closable="false"
            show-icon
            title="系统内置模板必须保留上方全部变量，变量名拼写错误也会被后端拒绝。"
            class="prompt-variable-alert"
          />

          <ElFormItem label="System Prompt" prop="systemPrompt">
            <ElInput
              v-model="model.systemPrompt"
              type="textarea"
              :rows="7"
              resize="vertical"
              placeholder="定义 AI 的角色、边界、回答原则和安全约束"
            />
          </ElFormItem>
          <ElFormItem label="User Prompt" prop="userPrompt">
            <ElInput
              v-model="model.userPrompt"
              type="textarea"
              :rows="11"
              resize="vertical"
              placeholder="组合知识上下文、用户问题等运行时变量"
            />
          </ElFormItem>
        </section>
      </ElForm>
    </div>

    <template #footer>
      <ElButton @click="closeDrawer">取消</ElButton>
      <ElButton :disabled="loading" @click="openPreview">预览最终内容</ElButton>
      <ElButton type="primary" :loading="submitting" :disabled="loading" @click="handleSubmit">保存模板</ElButton>
    </template>
  </ElDrawer>

  <ElDialog v-model="previewVisible" title="Prompt 最终渲染预览" width="760px" append-to-body>
    <ElAlert type="info" :closable="false" title="这里只替换示例变量，不会调用 AI，也不会产生 Token 费用。" />
    <ElForm label-position="top" class="prompt-preview-form">
      <ElFormItem v-for="variable in actualVariables" :key="variable" :label="`{${variable}}`">
        <ElInput v-model="previewVariables[variable]" type="textarea" :rows="2" />
      </ElFormItem>
    </ElForm>
    <template v-if="previewResult">
      <h4>System Prompt</h4>
      <pre class="prompt-preview-text">{{ previewResult.renderedSystemPrompt }}</pre>
      <h4>User Prompt</h4>
      <pre class="prompt-preview-text">{{ previewResult.renderedUserPrompt }}</pre>
    </template>
    <template #footer>
      <ElButton @click="previewVisible = false">关闭</ElButton>
      <ElButton type="primary" :loading="previewing" @click="renderPreview">生成预览</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="scss">
.prompt-operate-drawer .el-drawer__header {
  margin-bottom: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 18px 20px;
}

.prompt-operate-drawer .el-drawer__body {
  padding: 0;
}

.prompt-operate-drawer .el-drawer__footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 20px;
}

.prompt-drawer-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.prompt-drawer-heading__icon {
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

.prompt-drawer-heading strong,
.prompt-drawer-heading small,
.prompt-switch-row strong,
.prompt-switch-row small {
  display: block;
}

.prompt-drawer-heading strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.prompt-drawer-heading small,
.prompt-form-hint,
.prompt-switch-row small,
.prompt-section-heading p {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.prompt-drawer-heading small,
.prompt-form-hint,
.prompt-switch-row small {
  margin-top: 3px;
}

.prompt-drawer-body {
  min-height: 240px;
}

.prompt-form-section {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 20px;
}

.prompt-form-section h3 {
  margin: 0 0 18px;
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 650;
}

.prompt-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.prompt-form .el-form-item {
  margin-bottom: 18px;
}

.prompt-form-hint {
  margin-bottom: 0;
}

.prompt-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
}

.prompt-switch-row strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 550;
}

.prompt-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.prompt-section-heading h3 {
  margin-bottom: 4px;
}

.prompt-section-heading p {
  margin: 0;
}

.prompt-section-heading code {
  border-radius: 4px;
  background: var(--el-fill-color);
  padding: 1px 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.prompt-variable-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.prompt-variable-list > span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.prompt-variable-list .el-tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.prompt-variable-alert {
  margin-bottom: 18px;
}

.prompt-form textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1.65;
}

.prompt-preview-form {
  margin-top: 16px;
}
.prompt-preview-text {
  max-height: 260px;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-light);
  padding: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 700px) {
  .prompt-operate-drawer {
    width: 94% !important;
  }

  .prompt-form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .prompt-section-heading {
    flex-direction: column;
  }

  .prompt-variable-list {
    justify-content: flex-start;
  }
}
</style>
