<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import type { FormInstance, FormRules } from 'element-plus';
import {
  fetchCreateProjectModule,
  fetchDeleteProjectModule,
  fetchGetProjectList,
  fetchGetProjectModules,
  fetchUpdateProjectModule
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'ProjectModules' });

const authStore = useAuthStore();
const loading = ref(false);
const projectLoading = ref(false);
const submitting = ref(false);
const keyword = ref('');
const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const parentId = ref<number | null>(null);
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const modules = ref<Api.ProjectManage.ProjectModule[]>([]);
const formRef = ref<FormInstance>();
const form = reactive({ name: '', code: '', description: '' });

const projectOptions = computed(() => {
  return projects.value.map(item => ({ label: item.name, value: item.id }));
});
const activeProject = computed(() => projects.value.find(item => item.id === activeProjectId.value));
const isArchivedProject = computed(() => activeProject.value?.status === 'ARCHIVED');
const canManageModules = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:module:manage');
});

const rules: FormRules = {
  name: [{ required: true, message: '请输入模块名称', trigger: 'blur' }],
  code: [
    { required: true, message: '请输入模块标识', trigger: 'blur' },
    { pattern: /^[A-Z][A-Z0-9_]{1,31}$/, message: '使用 2–32 位大写字母、数字或下划线', trigger: 'blur' }
  ]
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
    modules.value = [];
    return;
  }

  loading.value = true;
  const { data, error } = await fetchGetProjectModules(activeProjectId.value, {
    keyword: keyword.value.trim()
  });
  loading.value = false;

  if (!error) modules.value = data;
}

async function handleProjectChange() {
  keyword.value = '';
  await getData();
}

const handleKeywordChange = useDebounceFn(getData, 300);

function openDialog(data?: Api.ProjectManage.ProjectModule, targetParentId: number | null = null) {
  if (!activeProjectId.value) {
    window.$message?.warning('请先选择项目');
    return;
  }
  if (isArchivedProject.value) {
    window.$message?.warning('已归档项目不能管理模块');
    return;
  }
  editingId.value = data?.id ?? null;
  parentId.value = data ? data.parentId : targetParentId;
  Object.assign(
    form,
    data ? { name: data.name, code: data.code, description: data.description } : { name: '', code: '', description: '' }
  );
  dialogVisible.value = true;
}

async function submitForm() {
  await formRef.value?.validate();
  if (!activeProjectId.value) return;

  submitting.value = true;
  const normalizedForm = {
    name: form.name.trim(),
    code: form.code.trim().toUpperCase(),
    description: form.description.trim()
  };
  const { error } = editingId.value
    ? await fetchUpdateProjectModule(activeProjectId.value, editingId.value, normalizedForm)
    : await fetchCreateProjectModule(activeProjectId.value, {
        ...normalizedForm,
        parentId: parentId.value,
        orderNo: 0
      });
  submitting.value = false;

  if (error) return;

  dialogVisible.value = false;
  window.$message?.success(editingId.value ? '模块已更新' : '模块已创建');
  await Promise.all([getData(), getProjects()]);
}

async function removeModule(row: Api.ProjectManage.ProjectModule) {
  if (!activeProjectId.value) return;

  const { error } = await fetchDeleteProjectModule(activeProjectId.value, row.id);
  if (error) return;

  window.$message?.success('模块已删除');
  await Promise.all([getData(), getProjects()]);
}

async function initialize() {
  await getProjects();
  await getData();
}

initialize();
</script>

<template>
  <div class="project-page">
    <ElCard class="project-card module-card">
      <template #header>
        <div class="project-page-header">
          <div class="project-page-title">
            <h2>功能模块</h2>
            <p>以树形结构维护项目功能边界，知识、需求和用例均可关联模块</p>
          </div>
          <div class="project-page-actions">
            <ElButton
              v-if="canManageModules"
              type="primary"
              :disabled="!activeProjectId || isArchivedProject"
              @click="openDialog()"
            >
              <template #icon><icon-ic-round-plus /></template>
              新建一级模块
            </ElButton>
          </div>
        </div>
      </template>

      <div class="project-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-selector"
          placeholder="选择项目"
          :loading="projectLoading"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projectOptions" :key="item.value" :label="item.label" :value="item.value" />
        </ElSelect>
        <ElInput
          v-model="keyword"
          clearable
          class="project-search"
          placeholder="搜索模块名称、标识或说明"
          @input="handleKeywordChange"
          @clear="getData"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
      </div>

      <div class="module-table-head">
        <span>模块名称</span>
        <span>模块说明</span>
        <span>关联资产</span>
        <span>操作</span>
      </div>
      <div v-loading="loading" class="module-tree-wrap">
        <ElTree
          :data="modules"
          node-key="id"
          default-expand-all
          :expand-on-click-node="false"
          :indent="28"
          empty-text="当前项目暂无功能模块"
        >
          <template #default="{ data }: { data: Api.ProjectManage.ProjectModule }">
            <div class="module-row">
              <div class="module-identity">
                <span class="module-icon"><SvgIcon icon="mdi:cube-outline" /></span>
                <span>
                  <strong>{{ data.name }}</strong>
                  <code>{{ data.code }}</code>
                </span>
              </div>
              <span class="module-description">{{ data.description || '—' }}</span>
              <span class="module-assets">{{ data.assetCount }} 项</span>
              <div class="table-row-actions module-actions" @click.stop>
                <ElTooltip v-if="canManageModules" content="添加子模块" placement="top">
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :disabled="isArchivedProject"
                    @click="openDialog(undefined, data.id)"
                  >
                    <icon-ic-round-plus />
                  </ElButton>
                </ElTooltip>
                <ElTooltip v-if="canManageModules" content="编辑" placement="top">
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :disabled="isArchivedProject"
                    @click="openDialog(data)"
                  >
                    <icon-material-symbols-edit-outline-rounded />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm
                  v-if="canManageModules"
                  :title="data.children?.length ? '将同时删除全部子模块，确认继续？' : '确认删除该模块？'"
                  @confirm="removeModule(data)"
                >
                  <template #reference>
                    <ElButton text circle class="table-row-action is-danger" :disabled="isArchivedProject">
                      <icon-ic-round-delete />
                    </ElButton>
                  </template>
                </ElPopconfirm>
              </div>
            </div>
          </template>
        </ElTree>
      </div>
    </ElCard>

    <ElDialog
      v-model="dialogVisible"
      :title="editingId ? '编辑功能模块' : parentId ? '添加子模块' : '新建一级模块'"
      width="520px"
      destroy-on-close
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="模块名称" prop="name">
          <ElInput v-model="form.name" placeholder="例如：支付订单" />
        </ElFormItem>
        <ElFormItem label="模块标识" prop="code">
          <ElInput v-model="form.code" placeholder="例如：PAY_ORDER" @input="form.code = form.code.toUpperCase()" />
        </ElFormItem>
        <ElFormItem label="模块说明" prop="description">
          <ElInput v-model="form.description" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style src="../shared.scss" lang="scss"></style>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style scoped lang="scss">
.module-card {
  display: flex;
  overflow: hidden;
  flex-direction: column;
}
.module-card :deep(.el-card__body) {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  padding: 0;
}
.module-table-head {
  display: grid;
  flex: none;
  grid-template-columns: minmax(280px, 1.25fr) minmax(220px, 1fr) 100px 118px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-extra-light);
  padding: 11px 18px 11px 50px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 550;
}
.module-tree-wrap {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 6px 0;
}
.module-tree-wrap :deep(.el-tree-node__content) {
  height: 56px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  padding-right: 16px;
}
.module-tree-wrap :deep(.el-tree-node__content:hover) {
  background: var(--el-fill-color-extra-light);
}
.module-row {
  display: grid;
  align-items: center;
  width: 100%;
  min-width: 720px;
  grid-template-columns: minmax(240px, 1.25fr) minmax(220px, 1fr) 100px 118px;
}
.module-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.module-identity > span:last-child {
  display: flex;
  min-width: 0;
  flex-direction: column;
}
.module-identity strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 600;
}
.module-identity code {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.module-icon {
  display: inline-flex;
  flex: 0 0 30px;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  background: rgb(var(--primary-color) / 8%);
  color: rgb(var(--primary-color));
}
.module-description,
.module-assets {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.module-actions {
  justify-content: flex-start;
}
@media (max-width: 800px) {
  .module-table-head {
    display: none;
  }
  .module-tree-wrap {
    overflow-x: hidden;
  }
  .module-tree-wrap :deep(.el-tree-node__content) {
    height: auto;
    min-height: 78px;
    align-items: stretch;
    padding: 8px 8px 8px 0;
  }
  .module-row {
    min-width: 0;
    grid-template-areas:
      'identity actions'
      'description assets';
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px 10px;
  }
  .module-identity {
    grid-area: identity;
  }
  .module-description {
    grid-area: description;
    padding-left: 40px;
  }
  .module-assets {
    grid-area: assets;
    align-self: center;
  }
  .module-actions {
    grid-area: actions;
    align-self: center;
    justify-content: flex-end;
  }
}
</style>
