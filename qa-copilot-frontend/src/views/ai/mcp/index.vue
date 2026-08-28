<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import { fetchCallMcpTool, fetchGetMcpServerInfo } from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'AiMcpManagement' });

type JsonSchemaProperty = Api.McpManagement.JsonSchemaProperty;
type ToolArgument = string | number | boolean | undefined;

type ToolField = {
  key: string;
  label: string;
  required: boolean;
  schema: JsonSchemaProperty;
};

const authStore = useAuthStore();
const isMobile = useMediaQuery('(max-width: 760px)');
const loading = ref(false);
const invoking = ref(false);
const drawerVisible = ref(false);
const serverInfo = ref<Api.McpManagement.ServerInfo | null>(null);
const activeTool = ref<Api.McpManagement.Tool | null>(null);
const callResult = ref<Record<string, unknown> | null>(null);
const callArguments = reactive<Record<string, ToolArgument>>({});

const canInvoke = computed(() => {
  const buttons = authStore.userInfo.buttons || [];
  return buttons.includes('*') || buttons.includes('mcp:invoke');
});

const fieldLabelMap: Record<string, string> = {
  project_id: '项目 ID',
  requirement_id: '需求 ID',
  module_id: '功能模块 ID',
  keyword: '关键词',
  status: '状态',
  source: '用例来源',
  current: '当前页',
  size: '每页条数'
};

/**
 * 功能：解析 Pydantic 生成的 JSON Schema 引用和可空联合类型，得到真正用于渲染表单的字段定义。
 * 作用：让枚举、可空枚举和普通字段都能由同一套页面组件自动展示。
 * 为什么用它：后端参数模型才是工具参数的唯一事实来源，前端动态读取可避免每新增一个工具就复制一份表单。
 */
function resolveSchema(property: JsonSchemaProperty, inputSchema: Api.McpManagement.InputSchema) {
  const candidate = property.anyOf?.find(item => item.type !== 'null') || property;
  if (!candidate.$ref) return { ...property, ...candidate };
  const definitionName = candidate.$ref.split('/').at(-1);
  const definition = definitionName ? inputSchema.$defs?.[definitionName] : undefined;
  return { ...property, ...candidate, ...(definition || {}) };
}

const toolFields = computed<ToolField[]>(() => {
  if (!activeTool.value) return [];
  const inputSchema = activeTool.value.inputSchema;
  const requiredFields = new Set(inputSchema.required || []);
  return Object.entries(inputSchema.properties || {}).map(([key, property]) => {
    const schema = resolveSchema(property, inputSchema);
    return {
      key,
      label: fieldLabelMap[key] || schema.title || key,
      required: requiredFields.has(key),
      schema
    };
  });
});

const formattedResult = computed(() => (callResult.value ? JSON.stringify(callResult.value, null, 2) : ''));

/**
 * 功能：读取 MCP 服务连接信息和当前登录用户可见的工具目录。
 * 作用：页面初始化和手动刷新都调用它，后端会同时完成权限过滤。
 * 为什么用它：工具可见性不能只靠前端隐藏，必须每次由后端根据实时角色权限返回。
 */
async function loadServerInfo() {
  loading.value = true;
  const { data, error } = await fetchGetMcpServerInfo();
  loading.value = false;
  if (!error) serverInfo.value = data;
}

/** 将连接地址写入系统剪贴板，方便粘贴到外部 MCP 客户端。 */
async function copyEndpoint() {
  if (!serverInfo.value?.endpoint) return;
  await navigator.clipboard.writeText(serverInfo.value.endpoint);
  window.$message?.success('MCP 地址已复制');
}

/**
 * 功能：打开工具试调用抽屉，并根据参数 Schema 填入后端声明的默认值。
 * 作用：为本次调用准备独立参数，避免上一个工具的字段残留。
 * 为什么用它：默认分页等参数由后端模型统一声明，页面不再重复维护默认值。
 */
function openTool(tool: Api.McpManagement.Tool) {
  activeTool.value = tool;
  callResult.value = null;
  Object.keys(callArguments).forEach(key => delete callArguments[key]);
  Object.entries(tool.inputSchema.properties || {}).forEach(([key, property]) => {
    const schema = resolveSchema(property, tool.inputSchema);
    if (['string', 'number', 'boolean'].includes(typeof schema.default)) {
      callArguments[key] = schema.default as ToolArgument;
    }
  });
  drawerVisible.value = true;
}

/**
 * 功能：删除未填写的可选参数，只提交用户明确填写的值。
 * 作用：让后端 Pydantic 参数模型继续应用默认值，同时保留 false 和 0 这类合法输入。
 * 为什么用它：直接提交空字符串会把“未填写”误当成业务值，尤其会导致可空数字或枚举校验失败。
 */
function buildArguments() {
  return Object.fromEntries(
    Object.entries(callArguments).filter(([, value]) => value !== undefined && value !== null && value !== '')
  );
}

/**
 * 功能：校验必填字段并通过管理接口执行一次真实的只读 MCP 工具调用。
 * 作用：帮助管理员在接入外部客户端前验证参数、业务权限和返回结构。
 * 为什么用它：试调用复用后端 MCP 管理 Service，不在浏览器中模拟结果，因此与协议入口的业务行为一致。
 */
async function invokeTool() {
  if (!activeTool.value) return;
  const argumentsPayload = buildArguments();
  const missingField = toolFields.value.find(field => field.required && argumentsPayload[field.key] === undefined);
  if (missingField) {
    window.$message?.warning(`请填写${missingField.label}`);
    return;
  }
  invoking.value = true;
  const { data, error } = await fetchCallMcpTool(activeTool.value.code, argumentsPayload);
  invoking.value = false;
  if (!error) {
    callResult.value = data.result;
    window.$message?.success('工具调用成功');
  }
}

function riskLabel(risk: Api.McpManagement.RiskLevel) {
  return { LOW: '低风险', MEDIUM: '中风险', HIGH: '高风险' }[risk];
}

onMounted(loadServerInfo);
</script>

<template>
  <div class="mcp-page">
    <ElCard shadow="never" class="overview-card">
      <div class="page-header">
        <div class="title-group">
          <span class="title-icon"><SvgIcon icon="mdi:connection" /></span>
          <div>
            <div class="title-line">
              <h2>MCP 管理</h2>
              <ElTag :type="serverInfo?.enabled ? 'success' : 'danger'" effect="light" round>
                {{ serverInfo?.enabled ? '服务已启用' : '服务未启用' }}
              </ElTag>
            </div>
            <p>管理 Model Context Protocol（模型上下文协议）连接，并验证当前账号可调用的只读工具。</p>
          </div>
        </div>
        <ElButton :loading="loading" @click="loadServerInfo">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新
        </ElButton>
      </div>

      <ElAlert
        class="security-alert"
        type="info"
        :closable="false"
        show-icon
        title="外部客户端需要在 Authorization 请求头中携带当前平台签发的 Bearer Access Token；工具仍会执行菜单权限和项目数据权限校验。"
      />

      <ElSkeleton :loading="loading && !serverInfo" animated>
        <div v-if="serverInfo" class="connection-grid">
          <div class="connection-item endpoint-item">
            <span class="connection-label">服务地址</span>
            <div class="endpoint-value">
              <code>{{ serverInfo.endpoint }}</code>
              <ElButton link type="primary" @click="copyEndpoint">
                <SvgIcon icon="mdi:content-copy" />
                复制
              </ElButton>
            </div>
          </div>
          <div class="connection-item">
            <span class="connection-label">传输方式</span>
            <strong>{{ serverInfo.transport }}</strong>
          </div>
          <div class="connection-item">
            <span class="connection-label">身份认证</span>
            <strong>{{ serverInfo.authScheme }}</strong>
          </div>
          <div class="connection-item">
            <span class="connection-label">可用工具</span>
            <strong>{{ serverInfo.tools.length }} 个</strong>
          </div>
        </div>
      </ElSkeleton>
    </ElCard>

    <ElCard shadow="never" class="tools-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>工具目录</h3>
            <p>这里只展示当前账号同时具备菜单权限和业务权限的工具。</p>
          </div>
          <span>{{ serverInfo?.tools.length || 0 }} 个工具</span>
        </div>
      </template>

      <ElEmpty v-if="!loading && !serverInfo?.tools.length" description="当前账号没有可用 MCP 工具" />
      <div v-else class="tool-grid">
        <article v-for="tool in serverInfo?.tools || []" :key="tool.code" class="tool-card">
          <div class="tool-card-header">
            <span class="tool-icon"><SvgIcon icon="mdi:tools" /></span>
            <div class="tool-heading">
              <strong>{{ tool.name }}</strong>
              <code>{{ tool.code }}</code>
            </div>
            <ElTag type="success" effect="plain" size="small">{{ riskLabel(tool.riskLevel) }}</ElTag>
          </div>
          <p class="tool-description">{{ tool.description }}</p>
          <div class="tool-footer">
            <div class="tool-meta">
              <ElTag v-if="tool.readOnly" type="info" effect="plain" size="small">只读</ElTag>
              <span>权限：{{ tool.requiredPermission }}</span>
            </div>
            <ElButton type="primary" plain :disabled="!canInvoke" @click="openTool(tool)">试调用</ElButton>
          </div>
        </article>
      </div>
    </ElCard>

    <ElDrawer
      v-model="drawerVisible"
      :size="isMobile ? '100%' : '620px'"
      destroy-on-close
      class="mcp-call-drawer"
    >
      <template #header>
        <div v-if="activeTool" class="drawer-title">
          <span class="tool-icon"><SvgIcon icon="mdi:play-box-outline" /></span>
          <div>
            <strong>试调用：{{ activeTool.name }}</strong>
            <code>{{ activeTool.code }}</code>
          </div>
        </div>
      </template>

      <template v-if="activeTool">
        <ElAlert
          type="warning"
          :closable="false"
          show-icon
          title="这是一次真实调用，会读取当前数据库数据，但当前开放工具均不会修改业务数据。"
        />

        <ElForm label-position="top" class="tool-form">
          <ElFormItem
            v-for="field in toolFields"
            :key="field.key"
            :label="field.label"
            :required="field.required"
          >
            <ElSelect
              v-if="field.schema.enum?.length"
              v-model="callArguments[field.key]"
              clearable
              filterable
              :placeholder="field.schema.description || `请选择${field.label}`"
            >
              <ElOption v-for="option in field.schema.enum" :key="String(option)" :label="String(option)" :value="option" />
            </ElSelect>
            <ElInputNumber
              v-else-if="field.schema.type === 'integer' || field.schema.type === 'number'"
              v-model="callArguments[field.key] as number"
              :min="field.key === 'current' || field.key === 'size' ? 1 : undefined"
              controls-position="right"
              class="w-full"
            />
            <ElSwitch v-else-if="field.schema.type === 'boolean'" v-model="callArguments[field.key] as boolean" />
            <ElInput
              v-else
              v-model="callArguments[field.key] as string"
              clearable
              :placeholder="field.schema.description || `请输入${field.label}`"
            />
            <div class="field-hint">
              参数名：<code>{{ field.key }}</code>
              <span v-if="field.schema.description"> · {{ field.schema.description }}</span>
            </div>
          </ElFormItem>
        </ElForm>

        <div class="call-actions">
          <ElButton type="primary" :loading="invoking" :disabled="!canInvoke" @click="invokeTool">
            <template #icon><SvgIcon icon="mdi:play" /></template>
            执行调用
          </ElButton>
        </div>

        <section v-if="callResult" class="result-panel">
          <div class="result-title">
            <strong>调用结果</strong>
            <ElTag type="success" size="small">成功</ElTag>
          </div>
          <pre>{{ formattedResult }}</pre>
        </section>
      </template>
    </ElDrawer>
  </div>
</template>

<style scoped>
.mcp-page {
  display: grid;
  gap: 16px;
  min-height: 100%;
}

.overview-card,
.tools-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
}

.page-header,
.section-header,
.title-group,
.title-line,
.endpoint-value,
.tool-card-header,
.tool-footer,
.tool-meta,
.drawer-title,
.result-title {
  display: flex;
  align-items: center;
}

.page-header,
.section-header,
.tool-footer,
.result-title {
  justify-content: space-between;
}

.title-group {
  gap: 14px;
}

.title-icon,
.tool-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 10px;
}

.title-icon {
  width: 44px;
  height: 44px;
  font-size: 24px;
}

.tool-icon {
  width: 36px;
  height: 36px;
  font-size: 19px;
}

.title-line {
  gap: 10px;
}

h2,
h3,
p {
  margin: 0;
}

h2 {
  font-size: 20px;
}

h3 {
  font-size: 16px;
}

.title-group p,
.section-header p {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.security-alert {
  margin-top: 20px;
}

.connection-grid {
  display: grid;
  grid-template-columns: minmax(300px, 2fr) repeat(3, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.connection-item {
  min-width: 0;
  padding: 14px 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 9px;
}

.connection-label {
  display: block;
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.endpoint-value {
  gap: 8px;
}

.endpoint-value code {
  overflow: hidden;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-header > span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.tool-card {
  display: flex;
  flex-direction: column;
  min-height: 190px;
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.tool-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 8px 24px rgb(31 35 48 / 6%);
  transform: translateY(-1px);
}

.tool-card-header {
  gap: 12px;
}

.tool-heading {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 4px;
}

.tool-heading code,
.drawer-title code {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.tool-description {
  flex: 1;
  margin: 14px 0 18px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.65;
}

.tool-meta {
  flex-wrap: wrap;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.drawer-title {
  gap: 12px;
}

.drawer-title > div {
  display: grid;
  gap: 4px;
}

.tool-form {
  margin-top: 22px;
}

.field-hint {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.call-actions {
  display: flex;
  justify-content: flex-end;
  margin: 4px 0 22px;
}

.result-panel {
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 9px;
}

.result-title {
  padding: 12px 14px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.result-panel pre {
  max-height: 440px;
  padding: 16px;
  margin: 0;
  overflow: auto;
  color: var(--el-text-color-primary);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--el-bg-color);
}

@media (max-width: 1100px) {
  .connection-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .endpoint-item {
    grid-column: span 2;
  }
}

@media (max-width: 760px) {
  .page-header,
  .tool-footer {
    align-items: flex-start;
  }

  .page-header {
    gap: 12px;
  }

  .title-group {
    align-items: flex-start;
  }

  .title-line {
    flex-wrap: wrap;
  }

  .connection-grid,
  .tool-grid {
    grid-template-columns: 1fr;
  }

  .endpoint-item {
    grid-column: auto;
  }

  .endpoint-value {
    align-items: flex-start;
  }

  .endpoint-value code {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .tool-footer {
    gap: 12px;
  }
}
</style>
