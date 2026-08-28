<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import dayjs from 'dayjs';
import { fetchCreateFileTemplate, fetchGetFileTemplates, fetchUpdateFileTemplate } from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';
import ProjectSelector from '../components/project-selector.vue';

defineOptions({ name: 'ToolsFileTemplates' });
const authStore = useAuthStore();
const projectId = ref<number | null>(null);
const records = ref<Api.ToolManage.FileTemplate[]>([]);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const editing = ref<Api.ToolManage.FileTemplate | null>(null);
const form = reactive<Api.ToolManage.FileTemplateParams>({
  name: '',
  fileFormat: 'CSV',
  encoding: 'UTF-8',
  delimiter: ',',
  fields: [],
  headerConfig: {},
  trailerConfig: {},
  enabled: true
});
const canManage = computed(
  () => authStore.userInfo.buttons.includes('*') || authStore.userInfo.buttons.includes('tool:manage')
);
const formatLabels: Record<Api.ToolManage.FileFormat, string> = {
  CSV: 'CSV 逗号分隔',
  EXCEL: 'Excel 工作簿',
  FIXED_WIDTH_TXT: '固定宽度 TXT',
  DELIMITED_TXT: '自定义分隔 TXT',
  JSON: 'JSON',
  XML: 'XML'
};

function emptyField(): Api.ToolManage.TemplateField {
  return {
    name: '',
    sourceField: '',
    dataType: 'STRING',
    required: false,
    length: null,
    precision: null,
    format: null,
    padding: null,
    paddingChar: ' ',
    mapping: {}
  };
}
async function loadData() {
  if (!projectId.value) return;
  loading.value = true;
  const { data, error } = await fetchGetFileTemplates(projectId.value);
  loading.value = false;
  if (!error) records.value = data;
}
function open(row?: Api.ToolManage.FileTemplate) {
  editing.value = row ?? null;
  Object.assign(
    form,
    row
      ? {
          name: row.name,
          fileFormat: row.fileFormat,
          encoding: row.encoding,
          delimiter: row.delimiter,
          fields: structuredClone(row.fields),
          headerConfig: structuredClone(row.headerConfig),
          trailerConfig: structuredClone(row.trailerConfig),
          enabled: row.enabled
        }
      : {
          name: '',
          fileFormat: 'CSV',
          encoding: 'UTF-8',
          delimiter: ',',
          fields: [emptyField()],
          headerConfig: {},
          trailerConfig: {},
          enabled: true
        }
  );
  visible.value = true;
}
function addField() {
  form.fields.push(emptyField());
}
function removeField(index: number) {
  if (form.fields.length > 1) form.fields.splice(index, 1);
}
async function save() {
  if (!projectId.value || !form.name.trim()) return window.$message?.warning('请填写模板名称');
  if (form.fields.some(item => !item.name.trim() || !item.sourceField.trim()))
    return window.$message?.warning('请补全字段名称和来源字段');
  saving.value = true;
  const payload = structuredClone({ ...form, name: form.name.trim(), delimiter: form.delimiter || null });
  const result = editing.value
    ? await fetchUpdateFileTemplate(projectId.value, editing.value.id, payload)
    : await fetchCreateFileTemplate(projectId.value, payload);
  saving.value = false;
  if (result.error) return;
  visible.value = false;
  window.$message?.success(editing.value ? '模板已更新' : '模板已创建');
  await loadData();
}
watch(projectId, loadData);
onMounted(loadData);
</script>

<template>
  <div class="tool-page">
    <ElCard class="tool-card">
      <template #header>
        <div class="tool-heading">
          <div>
            <h2>文件模板</h2>
            <p>同一份字段规则同时用于文件生成与文件校验，避免两套规则逐渐不一致</p>
          </div>
          <div class="tool-actions">
            <ProjectSelector v-model="projectId" />
            <ElButton v-if="canManage" type="primary" @click="open()">
              <SvgIcon icon="mdi:plus" />
              新增模板
            </ElButton>
          </div>
        </div>
      </template>
      <ElTable v-loading="loading" border :data="records" row-key="id">
        <ElTableColumn label="模板" min-width="220">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <div class="template-sub">
              {{ formatLabels[row.fileFormat as Api.ToolManage.FileFormat] }} · {{ row.encoding }}
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="字段数" width="100" align="center">
          <template #default="{ row }">{{ row.fields.length }}</template>
        </ElTableColumn>
        <ElTableColumn label="字段预览" min-width="320">
          <template #default="{ row }">
            <ElTag v-for="field in row.fields.slice(0, 5)" :key="field.name" class="field-tag" size="small">
              {{ field.name }} / {{ field.dataType }}
            </ElTag>
            <span v-if="row.fields.length > 5">…</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="更新时间" width="160">
          <template #default="{ row }">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</template>
        </ElTableColumn>
        <ElTableColumn v-if="canManage" label="操作" width="80" fixed="right" align="center">
          <template #default="{ row }">
            <ElButton text circle @click="open(row)"><SvgIcon icon="mdi:pencil-outline" /></ElButton>
          </template>
        </ElTableColumn>
        <template #empty><ElEmpty description="当前项目暂无文件模板" /></template>
      </ElTable>
    </ElCard>

    <ElDrawer v-model="visible" size="80%" :title="editing ? '编辑文件模板' : '新增文件模板'" class="template-drawer">
      <ElForm label-position="top">
        <div class="template-basic">
          <ElFormItem label="模板名称" required><ElInput v-model="form.name" /></ElFormItem>
          <ElFormItem label="文件格式" required>
            <ElSelect v-model="form.fileFormat" class="w-full">
              <ElOption v-for="(label, value) in formatLabels" :key="value" :label="label" :value="value" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="编码">
            <ElSelect v-model="form.encoding" class="w-full">
              <ElOption label="UTF-8" value="UTF-8" />
              <ElOption label="GBK" value="GBK" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem v-if="form.fileFormat === 'DELIMITED_TXT' || form.fileFormat === 'CSV'" label="分隔符">
            <ElInput v-model="form.delimiter" maxlength="10" />
          </ElFormItem>
        </div>
        <div class="field-title">
          <div>
            <h3>字段规则</h3>
            <p>来源字段对应生成任务每条记录中的键；长度、精度、日期格式也用于反向校验。</p>
          </div>
          <ElButton type="primary" plain @click="addField">
            <SvgIcon icon="mdi:plus" />
            添加字段
          </ElButton>
        </div>
        <div class="field-table-wrap">
          <table class="field-table">
            <thead>
              <tr>
                <th>输出名称</th>
                <th>来源字段</th>
                <th>数据类型</th>
                <th>必填</th>
                <th>长度</th>
                <th>精度</th>
                <th>日期格式</th>
                <th>补位</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(field, index) in form.fields" :key="index">
                <td><ElInput v-model="field.name" /></td>
                <td><ElInput v-model="field.sourceField" /></td>
                <td>
                  <ElSelect v-model="field.dataType">
                    <ElOption
                      v-for="type in ['STRING', 'INTEGER', 'DECIMAL', 'DATE', 'DATETIME', 'BOOLEAN']"
                      :key="type"
                      :label="type"
                      :value="type"
                    />
                  </ElSelect>
                </td>
                <td><ElSwitch v-model="field.required" /></td>
                <td><ElInputNumber v-model="field.length" :min="1" :max="10000" controls-position="right" /></td>
                <td>
                  <ElInputNumber
                    v-model="field.precision"
                    :min="0"
                    :max="18"
                    :disabled="field.dataType !== 'DECIMAL'"
                    controls-position="right"
                  />
                </td>
                <td><ElInput v-model="field.format" placeholder="YYYY-MM-DD" /></td>
                <td>
                  <ElSelect v-model="field.padding" clearable>
                    <ElOption label="左补位" value="LEFT" />
                    <ElOption label="右补位" value="RIGHT" />
                  </ElSelect>
                </td>
                <td>
                  <ElButton text circle type="danger" :disabled="form.fields.length === 1" @click="removeField(index)">
                    <SvgIcon icon="mdi:delete-outline" />
                  </ElButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <ElFormItem label="启用模板"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="visible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="save">保存模板</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style src="../shared.scss" scoped lang="scss"></style>

<style scoped lang="scss">
.template-sub {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.field-tag {
  margin: 2px 5px 2px 0;
}
.template-basic {
  display: grid;
  grid-template-columns: 2fr 1.4fr 1fr 1fr;
  gap: 12px;
}
.field-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 10px 0;
}
.field-title h3 {
  margin: 0;
  font-size: 14px;
}
.field-title p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.field-table-wrap {
  overflow: auto;
  margin-bottom: 18px;
}
.field-table {
  width: 100%;
  min-width: 1250px;
  border-collapse: collapse;
}
.field-table th,
.field-table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 8px;
  text-align: left;
}
.field-table th {
  background: var(--el-fill-color-lighter);
  font-size: 12px;
}
@media (max-width: 800px) {
  .template-basic {
    grid-template-columns: 1fr;
  }
}
</style>
