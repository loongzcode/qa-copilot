<script setup lang="ts">
import { nextTick, reactive, ref, watch } from 'vue';
import { createAutomationStepTemplateText } from '@/utils/automation-test-case';

type KeyValueRow = { key: string; value: string };
type AssertionType =
  | 'STATUS_CODE'
  | 'JSON_PATH_EQUALS'
  | 'JSON_PATH_EXISTS'
  | 'HEADER_EQUALS'
  | 'BODY_CONTAINS'
  | 'RESPONSE_TIME_LE';
type AssertionRow = { type: AssertionType; expression: string; expected: string };
type ExtractorRow = { name: string; source: 'JSON_BODY' | 'HEADER'; expression: string };

type EditorState = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS';
  path: string;
  timeoutSeconds: number;
  headers: KeyValueRow[];
  query: KeyValueRow[];
  bodyMode: 'NONE' | 'JSON' | 'FORM';
  jsonBody: string;
  formBody: KeyValueRow[];
  assertions: AssertionRow[];
  extractors: ExtractorRow[];
};

const model = defineModel<string>({ required: true });
const rawJson = ref('');
const syncingModel = ref(false);
/** 当前正在编辑的请求组成部分，只影响界面展示，不会写入自动化协议。 */
const activeRequestTab = ref<'PARAMS' | 'HEADERS' | 'BODY'>('PARAMS');

function emptyState(): EditorState {
  return {
    method: 'GET',
    path: '/api/example',
    timeoutSeconds: 30,
    headers: [],
    query: [],
    bodyMode: 'NONE',
    jsonBody: '{}',
    formBody: [],
    assertions: [{ type: 'STATUS_CODE', expression: '', expected: '200' }],
    extractors: []
  };
}

const state = reactive<EditorState>(emptyState());

const assertionOptions: Array<{ label: string; value: AssertionType }> = [
  { label: '状态码等于', value: 'STATUS_CODE' },
  { label: 'JSON 路径值等于', value: 'JSON_PATH_EQUALS' },
  { label: 'JSON 路径存在', value: 'JSON_PATH_EXISTS' },
  { label: '响应头等于', value: 'HEADER_EQUALS' },
  { label: '响应正文包含', value: 'BODY_CONTAINS' },
  { label: '响应时间不超过', value: 'RESPONSE_TIME_LE' }
];

function toRows(value: unknown): KeyValueRow[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.entries(value).map(([key, item]) => ({
    key,
    value: typeof item === 'string' ? item : JSON.stringify(item)
  }));
}

function displayValue(value: unknown) {
  if (value === undefined || value === null) return '';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function parseValue(value: string): unknown {
  const text = value.trim();
  if (!text) return '';
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function rowsToObject(rows: KeyValueRow[]) {
  return Object.fromEntries(rows.filter(row => row.key.trim()).map(row => [row.key.trim(), parseValue(row.value)]));
}

function assertionNeedsExpression(type: AssertionType) {
  return ['JSON_PATH_EQUALS', 'JSON_PATH_EXISTS', 'HEADER_EQUALS'].includes(type);
}

function assertionNeedsExpected(type: AssertionType) {
  return type !== 'JSON_PATH_EXISTS';
}

function serializeState() {
  const request: Record<string, unknown> = {
    method: state.method,
    path: state.path.trim(),
    headers: rowsToObject(state.headers),
    query: rowsToObject(state.query),
    timeoutSeconds: state.timeoutSeconds
  };
  if (state.bodyMode === 'JSON') request.jsonBody = parseValue(state.jsonBody);
  if (state.bodyMode === 'FORM') request.formBody = rowsToObject(state.formBody);

  return JSON.stringify(
    {
      request,
      assertions: state.assertions.map(assertion => {
        const result: Record<string, unknown> = { type: assertion.type };
        if (assertionNeedsExpression(assertion.type)) result.expression = assertion.expression.trim();
        if (assertionNeedsExpected(assertion.type)) {
          result.expected = ['STATUS_CODE', 'RESPONSE_TIME_LE'].includes(assertion.type)
            ? Number(assertion.expected)
            : parseValue(assertion.expected);
        }
        return result;
      }),
      extractors: state.extractors.map(extractor => ({
        name: extractor.name.trim(),
        source: extractor.source,
        expression: extractor.expression.trim()
      }))
    },
    null,
    2
  );
}

function hydrate(raw: string) {
  let parsed: Record<string, any>;
  try {
    const value = JSON.parse(raw || createAutomationStepTemplateText());
    parsed = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch {
    parsed = JSON.parse(createAutomationStepTemplateText()) as Record<string, any>;
  }
  const request = parsed.request && typeof parsed.request === 'object' ? parsed.request : {};
  const bodyMode = request.jsonBody !== undefined ? 'JSON' : request.formBody !== undefined ? 'FORM' : 'NONE';
  Object.assign(state, {
    method: request.method || 'GET',
    path: request.path || '/api/example',
    timeoutSeconds: request.timeoutSeconds || 30,
    headers: toRows(request.headers),
    query: toRows(request.query),
    bodyMode,
    jsonBody: request.jsonBody === undefined ? '{}' : displayValue(request.jsonBody),
    formBody: toRows(request.formBody),
    assertions:
      Array.isArray(parsed.assertions) && parsed.assertions.length
        ? parsed.assertions.map((item: Record<string, unknown>) => ({
            type: (item.type || 'STATUS_CODE') as AssertionType,
            expression: displayValue(item.expression),
            expected: displayValue(item.expected)
          }))
        : [{ type: 'STATUS_CODE', expression: '', expected: '200' }],
    extractors: Array.isArray(parsed.extractors)
      ? parsed.extractors.map((item: Record<string, unknown>) => ({
          name: displayValue(item.name),
          source: (item.source || 'JSON_BODY') as 'JSON_BODY' | 'HEADER',
          expression: displayValue(item.expression)
        }))
      : []
  });
  rawJson.value = JSON.stringify(parsed, null, 2);
  if (!raw.trim()) {
    syncingModel.value = true;
    model.value = serializeState();
    rawJson.value = model.value;
    void nextTick(() => {
      syncingModel.value = false;
    });
  }
}

function addKeyValue(rows: KeyValueRow[]) {
  rows.push({ key: '', value: '' });
}

/** 删除指定的键值配置行，供请求头、查询参数和表单正文共同使用。 */
function removeKeyValue(rows: KeyValueRow[], index: number) {
  rows.splice(index, 1);
}

function addAssertion() {
  state.assertions.push({ type: 'STATUS_CODE', expression: '', expected: '200' });
}

function addExtractor() {
  state.extractors.push({ name: '', source: 'JSON_BODY', expression: '$.data.id' });
}

function applyRawJson() {
  try {
    const parsed = JSON.parse(rawJson.value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
    syncingModel.value = true;
    model.value = JSON.stringify(parsed, null, 2);
    hydrate(model.value);
    void nextTick(() => {
      syncingModel.value = false;
    });
    window.$message?.success('高级 JSON 已应用到表单');
  } catch {
    window.$message?.error('JSON 格式不正确，请检查括号、引号和逗号');
  }
}

watch(
  state,
  () => {
    if (syncingModel.value) return;
    syncingModel.value = true;
    model.value = serializeState();
    rawJson.value = model.value;
    void nextTick(() => {
      syncingModel.value = false;
    });
  },
  { deep: true }
);

watch(
  model,
  value => {
    if (!syncingModel.value) hydrate(value);
  },
  { immediate: true }
);
</script>

<template>
  <div class="automation-editor">
    <section class="editor-section">
      <header>
        <strong>接口请求</strong>
        <span>系统会使用所选测试环境补全域名</span>
      </header>
      <div class="request-line">
        <ElSelect v-model="state.method" class="method-select">
          <ElOption
            v-for="method in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']"
            :key="method"
            :label="method"
            :value="method"
          />
        </ElSelect>
        <ElInput v-model="state.path" placeholder="接口路径，例如 /api/articles" />
        <ElInputNumber v-model="state.timeoutSeconds" :min="1" :max="60" controls-position="right" />
        <span class="unit">秒</span>
      </div>
    </section>

    <section class="editor-section request-parameter-section">
      <ElTabs v-model="activeRequestTab" class="request-tabs">
        <ElTabPane name="PARAMS">
          <template #label>
            <span class="request-tab-label">
              查询参数
              <em v-if="state.query.length">{{ state.query.length }}</em>
            </span>
          </template>
          <div class="parameter-table">
            <div class="parameter-table-header">
              <span>参数名</span>
              <span>参数值</span>
              <span>操作</span>
            </div>
            <div v-for="(row, index) in state.query" :key="index" class="key-value-row">
              <ElInput v-model="row.key" placeholder="例如 page" />
              <ElInput v-model="row.value" placeholder="例如 1 或 {{page}}" />
              <ElButton
                class="row-action-button"
                text
                circle
                type="danger"
                title="删除查询参数"
                @click.stop="removeKeyValue(state.query, index)"
              >
                <SvgIcon icon="mdi:delete-outline" />
              </ElButton>
            </div>
            <div v-if="!state.query.length" class="parameter-empty">暂无查询参数</div>
            <ElButton class="add-parameter-button" plain @click="addKeyValue(state.query)">
              <SvgIcon icon="mdi:plus" />
              添加查询参数
            </ElButton>
          </div>
        </ElTabPane>

        <ElTabPane name="HEADERS">
          <template #label>
            <span class="request-tab-label">
              请求头
              <em v-if="state.headers.length">{{ state.headers.length }}</em>
            </span>
          </template>
          <div class="parameter-table">
            <div class="parameter-table-header">
              <span>请求头名称</span>
              <span>请求头值</span>
              <span>操作</span>
            </div>
            <div v-for="(row, index) in state.headers" :key="index" class="key-value-row">
              <ElInput v-model="row.key" placeholder="例如 Authorization" />
              <ElInput v-model="row.value" placeholder="例如 Bearer {{access_token}}" />
              <ElButton
                class="row-action-button"
                text
                circle
                type="danger"
                title="删除请求头"
                @click.stop="removeKeyValue(state.headers, index)"
              >
                <SvgIcon icon="mdi:delete-outline" />
              </ElButton>
            </div>
            <div v-if="!state.headers.length" class="parameter-empty">暂无请求头，可在测试环境中配置公共请求头</div>
            <ElButton class="add-parameter-button" plain @click="addKeyValue(state.headers)">
              <SvgIcon icon="mdi:plus" />
              添加请求头
            </ElButton>
          </div>
        </ElTabPane>

        <ElTabPane name="BODY">
          <template #label>
            <span class="request-tab-label">
              请求正文
              <em v-if="state.bodyMode !== 'NONE'">1</em>
            </span>
          </template>
          <div class="body-config">
            <ElRadioGroup v-model="state.bodyMode">
              <ElRadioButton value="NONE">无正文</ElRadioButton>
              <ElRadioButton value="JSON">JSON</ElRadioButton>
              <ElRadioButton value="FORM">表单</ElRadioButton>
            </ElRadioGroup>
            <div v-if="state.bodyMode === 'NONE'" class="parameter-empty body-empty">
              当前请求不发送正文。GET 请求通常保持此选项。
            </div>
            <ElInput
              v-if="state.bodyMode === 'JSON'"
              v-model="state.jsonBody"
              class="body-editor"
              type="textarea"
              :rows="6"
              placeholder='例如 {"title":"测试文章"}'
            />
            <div v-if="state.bodyMode === 'FORM'" class="form-body-list">
              <div class="parameter-table-header">
                <span>字段名</span>
                <span>字段值</span>
                <span>操作</span>
              </div>
              <div v-for="(row, index) in state.formBody" :key="index" class="key-value-row">
                <ElInput v-model="row.key" placeholder="字段名" />
                <ElInput v-model="row.value" placeholder="字段值" />
                <ElButton
                  class="row-action-button"
                  text
                  circle
                  type="danger"
                  title="删除表单字段"
                  @click.stop="removeKeyValue(state.formBody, index)"
                >
                  <SvgIcon icon="mdi:delete-outline" />
                </ElButton>
              </div>
              <div v-if="!state.formBody.length" class="parameter-empty">暂无表单字段</div>
              <ElButton class="add-parameter-button" plain @click="addKeyValue(state.formBody)">
                <SvgIcon icon="mdi:plus" />
                添加表单字段
              </ElButton>
            </div>
          </div>
        </ElTabPane>
      </ElTabs>
    </section>

    <section class="editor-section assertion-section">
      <header>
        <strong>结果断言</strong>
        <span>至少一条，用来判断接口是否测试通过</span>
        <ElButton text type="primary" @click="addAssertion">添加断言</ElButton>
      </header>
      <div v-for="(assertion, index) in state.assertions" :key="index" class="assertion-row">
        <ElSelect v-model="assertion.type">
          <ElOption v-for="item in assertionOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElInput
          v-if="assertionNeedsExpression(assertion.type)"
          v-model="assertion.expression"
          :placeholder="assertion.type === 'HEADER_EQUALS' ? '响应头名称' : 'JSON 路径，例如 $.data.id'"
        />
        <ElInput
          v-if="assertionNeedsExpected(assertion.type)"
          v-model="assertion.expected"
          :placeholder="assertion.type === 'RESPONSE_TIME_LE' ? '最大毫秒数' : '预期值'"
        />
        <ElButton
          class="row-action-button"
          text
          circle
          type="danger"
          title="删除断言"
          :disabled="state.assertions.length === 1"
          @click.stop="state.assertions.splice(index, 1)"
        >
          <SvgIcon icon="mdi:close" />
        </ElButton>
      </div>
    </section>

    <ElCollapse class="config-collapse">
      <ElCollapseItem title="提取响应变量（高级，可选）" name="extractors">
        <div class="list-title">
          <span>把响应中的值保存给后续步骤使用</span>
          <ElButton text type="primary" @click="addExtractor">添加变量</ElButton>
        </div>
        <div v-for="(extractor, index) in state.extractors" :key="index" class="extractor-row">
          <ElInput v-model="extractor.name" placeholder="变量名，例如 article_id" />
          <ElSelect v-model="extractor.source">
            <ElOption label="JSON 正文" value="JSON_BODY" />
            <ElOption label="响应头" value="HEADER" />
          </ElSelect>
          <ElInput
            v-model="extractor.expression"
            :placeholder="extractor.source === 'JSON_BODY' ? '$.data.id' : 'Location'"
          />
          <ElButton
            class="row-action-button"
            text
            circle
            type="danger"
            title="删除提取变量"
            @click.stop="state.extractors.splice(index, 1)"
          >
            <SvgIcon icon="mdi:close" />
          </ElButton>
        </div>
      </ElCollapseItem>
      <ElCollapseItem title="高级 JSON（一般不需要）" name="raw-json">
        <ElInput v-model="rawJson" type="textarea" :rows="12" class="raw-editor" />
        <ElButton class="apply-json" type="primary" plain @click="applyRawJson">应用 JSON</ElButton>
      </ElCollapseItem>
    </ElCollapse>
  </div>
</template>

<style scoped lang="scss">
.automation-editor {
  display: grid;
  min-width: 0;
  gap: 12px;
  margin-top: 8px;
}
.editor-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  padding: 12px;
}
.editor-section header,
.list-title {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}
.editor-section header span,
.empty-tip,
.list-title > span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.editor-section header .el-button,
.list-title .el-button {
  margin-left: auto;
}
.request-line {
  display: grid;
  grid-template-columns: 105px minmax(220px, 1fr) 110px 20px;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.unit {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.config-collapse {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 0 12px;
}
.request-parameter-section {
  padding-top: 2px;
}
.request-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.request-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}
.request-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.request-tab-label em {
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-style: normal;
  line-height: 18px;
  text-align: center;
}
.parameter-table {
  display: grid;
  gap: 8px;
}
.parameter-table-header {
  display: grid;
  grid-template-columns: minmax(110px, 0.7fr) minmax(150px, 1.3fr) 42px;
  gap: 8px;
  padding: 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.key-value-row {
  display: grid;
  grid-template-columns: minmax(110px, 0.7fr) minmax(150px, 1.3fr) 32px;
  gap: 6px;
  margin-top: 6px;
}
.parameter-empty {
  padding: 14px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: center;
}
.add-parameter-button {
  width: 100%;
  border-style: dashed;
}
.body-config {
  display: grid;
  gap: 12px;
}
.body-empty {
  margin-top: 0;
}
.body-editor,
.form-body-list,
.assertion-row,
.extractor-row {
  margin-top: 10px;
}
.assertion-row {
  display: grid;
  grid-template-columns: 180px minmax(160px, 1fr) minmax(120px, 0.8fr) 32px;
  gap: 8px;
}
.extractor-row {
  display: grid;
  grid-template-columns: 1fr 130px 1.3fr 32px;
  gap: 8px;
}
.request-line > *,
.option-grid > *,
.key-value-row > *,
.assertion-row > *,
.extractor-row > * {
  min-width: 0;
}
.row-action-button {
  position: relative;
  z-index: 2;
  width: 32px;
  height: 32px;
  padding: 0;
}
.raw-editor :deep(textarea) {
  font-family: Consolas, 'Courier New', monospace;
}
.apply-json {
  margin-top: 8px;
}
@media (max-width: 700px) {
  .request-line,
  .assertion-row,
  .extractor-row {
    grid-template-columns: 1fr;
  }
  .parameter-table-header {
    display: none;
  }
  .key-value-row {
    grid-template-columns: 1fr 1fr 32px;
  }
  .unit {
    display: none;
  }
}
</style>
