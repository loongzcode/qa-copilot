<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchArchiveProject,
  fetchCreateProject,
  fetchGetFastApiUserList,
  fetchGetProjectList,
  fetchStartProject,
  fetchUpdateProject
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'ProjectInfo' });

type ProjectForm = Api.ProjectManage.ProjectCreateParams;
type ProjectStatusFilter = 'ALL' | Api.ProjectManage.ProjectStatus;

const authStore = useAuthStore();
const loading = ref(false);
const submitting = ref(false);
const ownerLoading = ref(false);
const records = ref<Api.ProjectManage.Project[]>([]);
const total = ref(0);
const dialogVisible = ref(false);
const operateType = ref<'add' | 'edit'>('add');
const editingProjectId = ref<number | null>(null);
const formRef = ref<FormInstance>();
const ownerOptions = ref<Api.SystemManage.FastApiUser[]>([]);
const statusFilter = ref<ProjectStatusFilter>('ALL');

const statusOptions: Array<{ label: string; value: ProjectStatusFilter }> = [
  { label: '全部', value: 'ALL' },
  { label: '未开始', value: 'DRAFT' },
  { label: '进行中', value: 'ACTIVE' },
  { label: '已归档', value: 'ARCHIVED' }
];

const searchParams = reactive<Api.ProjectManage.ProjectSearchParams>({
  current: 1,
  size: 10,
  keyword: ''
});

const form = reactive<ProjectForm>({
  name: '',
  code: '',
  description: '',
  ownerId: null
});

const rules: FormRules<ProjectForm> = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  code: [
    { required: true, message: '请输入项目标识', trigger: 'blur' },
    {
      pattern: /^[A-Z][A-Z0-9_-]{0,63}$/,
      message: '使用大写字母开头，可包含数字、下划线或连字符',
      trigger: 'blur'
    }
  ],
  ownerId: [{ required: true, message: '请选择项目负责人', trigger: 'change' }]
};

const currentUserId = computed(() => {
  const userId = Number(authStore.userInfo.userId);
  return Number.isInteger(userId) && userId > 0 ? userId : null;
});

const canQueryUsers = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('system:user:view');
});

const canCreateProject = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:info:create');
});

const canUpdateProject = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:info:update');
});

const canArchiveProject = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:info:archive');
});

const dialogTitle = computed(() => (operateType.value === 'add' ? '新建项目' : '编辑项目'));
const submitButtonText = computed(() => (operateType.value === 'add' ? '创建项目' : '保存修改'));

function statusLabel(status: Api.ProjectManage.ProjectStatus) {
  return {
    DRAFT: '未开始',
    ACTIVE: '进行中',
    ARCHIVED: '已归档'
  }[status];
}

function statusClass(status: Api.ProjectManage.ProjectStatus) {
  return {
    DRAFT: 'is-pending',
    ACTIVE: 'is-enabled',
    ARCHIVED: 'is-disabled'
  }[status];
}

async function getData() {
  loading.value = true;
  const { data, error } = await fetchGetProjectList({
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;

  if (error) return;

  records.value = data.records;
  total.value = data.total;
}

function addCurrentUserOption() {
  if (!currentUserId.value) return;

  ownerOptions.value = [
    {
      id: currentUserId.value,
      username: authStore.userInfo.userName,
      displayName: authStore.userInfo.userName,
      isActive: true,
      isSuperuser: false,
      roleIds: [],
      roleCodes: authStore.userInfo.roles,
      createdAt: '',
      updatedAt: ''
    }
  ];
}

async function getOwnerOptions() {
  addCurrentUserOption();

  // 普通项目用户通常没有“用户管理-查看”权限，此时只允许选择自己。
  if (!canQueryUsers.value) return;

  ownerLoading.value = true;
  const { data, error } = await fetchGetFastApiUserList({
    current: 1,
    size: 200,
    keyword: undefined
  });
  ownerLoading.value = false;

  if (!error) ownerOptions.value = data.records.filter(item => item.isActive);
}

function resetForm() {
  Object.assign(form, {
    name: '',
    code: '',
    description: '',
    ownerId: currentUserId.value
  });
  formRef.value?.clearValidate();
}

async function handleAdd() {
  operateType.value = 'add';
  editingProjectId.value = null;
  resetForm();
  dialogVisible.value = true;

  if (!ownerOptions.value.length) await getOwnerOptions();
}

async function handleEdit(project: Api.ProjectManage.Project) {
  operateType.value = 'edit';
  editingProjectId.value = project.id;
  Object.assign(form, {
    name: project.name,
    code: project.code,
    description: project.description,
    ownerId: project.ownerId
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;

  if (!ownerOptions.value.length) await getOwnerOptions();
}

async function handleSearch() {
  searchParams.current = 1;
  await getData();
}

async function handleStatusChange() {
  searchParams.status = statusFilter.value === 'ALL' ? undefined : statusFilter.value;
  searchParams.current = 1;
  await getData();
}

async function handleCurrentChange(current: number) {
  searchParams.current = current;
  await getData();
}

async function handleSizeChange(size: number) {
  searchParams.current = 1;
  searchParams.size = size;
  await getData();
}

async function handleArchive(project: Api.ProjectManage.Project) {
  const { error } = await fetchArchiveProject(project.id);
  if (error) return;

  window.$message?.success(`项目“${project.name}”已归档`);
  await getData();
}

async function handleStart(project: Api.ProjectManage.Project) {
  const { error } = await fetchStartProject(project.id);
  if (error) return;

  window.$message?.success(`项目“${project.name}”已开始`);
  await getData();
}

async function submitForm() {
  await formRef.value?.validate();

  submitting.value = true;
  const { error } =
    operateType.value === 'add'
      ? await fetchCreateProject({
          name: form.name.trim(),
          code: form.code.trim().toUpperCase(),
          description: form.description.trim(),
          ownerId: form.ownerId
        })
      : await fetchUpdateProject(editingProjectId.value!, {
          name: form.name.trim(),
          description: form.description.trim(),
          ownerId: form.ownerId
        });
  submitting.value = false;

  if (error) return;

  dialogVisible.value = false;
  window.$message?.success(operateType.value === 'add' ? '项目创建成功' : '项目更新成功');
  if (operateType.value === 'add') searchParams.current = 1;
  await getData();
}

getData();
</script>

<template>
  <div class="project-page manage-table-page">
    <ElCard class="project-card manage-table-card">
      <template #header>
        <div class="project-page-header">
          <div class="project-page-title">
            <h2>项目信息</h2>
            <p>统一维护测试项目及其负责人，项目是测试资产的隔离边界</p>
          </div>
          <div class="project-page-actions">
            <ElTooltip content="刷新" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <icon-mdi-refresh :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <ElButton v-if="canCreateProject" type="primary" @click="handleAdd">
              <template #icon><icon-ic-round-plus /></template>
              新建项目
            </ElButton>
          </div>
        </div>
      </template>

      <div class="project-toolbar">
        <ElInput
          v-model="searchParams.keyword"
          clearable
          class="project-search"
          placeholder="搜索项目名称、标识或负责人"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElButton type="primary" plain @click="handleSearch">查询</ElButton>
        <ElRadioGroup v-model="statusFilter" class="project-status-filter" @change="handleStatusChange">
          <ElRadioButton v-for="item in statusOptions" :key="item.value" :value="item.value">
            {{ item.label }}
          </ElRadioButton>
        </ElRadioGroup>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="id">
          <ElTableColumn label="项目" min-width="240">
            <template #default="{ row }">
              <div class="project-name-cell">
                <span class="project-name-icon"><SvgIcon icon="mdi:folder-outline" /></span>
                <span class="project-name-copy">
                  <strong>{{ row.name }}</strong>
                  <small>{{ row.code }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="description" label="项目说明" min-width="260" show-overflow-tooltip />
          <ElTableColumn label="负责人" width="120">
            <template #default="{ row }">
              {{ row.ownerName || '-' }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="成员 / 模块" width="130" align="center">
            <template #default="{ row }">
              <span class="project-secondary">{{ row.memberCount }} / {{ row.moduleCount }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="100" align="center">
            <template #default="{ row }">
              <span class="table-status" :class="statusClass(row.status)">
                <span />
                {{ statusLabel(row.status) }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" min-width="160">
            <template #default="{ row }">
              <span class="table-date">{{ dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn
            v-if="canUpdateProject || canArchiveProject"
            label="操作"
            width="112"
            align="right"
            fixed="right"
          >
            <template #default="{ row }">
              <div class="table-row-actions">
                <ElTooltip
                  v-if="canUpdateProject"
                  :content="row.status === 'ARCHIVED' ? '已归档项目不能编辑' : '编辑项目'"
                  placement="top"
                >
                  <ElButton
                    text
                    circle
                    class="table-row-action"
                    :disabled="row.status === 'ARCHIVED'"
                    @click="handleEdit(row)"
                  >
                    <icon-material-symbols-edit-outline-rounded />
                  </ElButton>
                </ElTooltip>
                <ElPopconfirm
                  v-if="row.status === 'DRAFT' && canUpdateProject"
                  width="240"
                  :title="`确认开始项目“${row.name}”吗？`"
                  confirm-button-text="确认开始"
                  cancel-button-text="取消"
                  @confirm="handleStart(row)"
                >
                  <template #reference>
                    <span class="project-state-action">
                      <ElTooltip content="开始项目" placement="top">
                        <ElButton text circle class="table-row-action">
                          <SvgIcon icon="material-symbols:play-arrow-rounded" />
                        </ElButton>
                      </ElTooltip>
                    </span>
                  </template>
                </ElPopconfirm>
                <ElPopconfirm
                  v-else-if="row.status === 'ACTIVE' && canArchiveProject"
                  width="260"
                  :title="`确认归档项目“${row.name}”吗？归档后将不能继续编辑。`"
                  confirm-button-text="确认归档"
                  cancel-button-text="取消"
                  @confirm="handleArchive(row)"
                >
                  <template #reference>
                    <span class="project-state-action">
                      <ElTooltip content="归档项目" placement="top">
                        <ElButton text circle class="table-row-action">
                          <SvgIcon icon="ph:archive-box-light" />
                        </ElButton>
                      </ElTooltip>
                    </span>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="暂无项目" :image-size="72" /></template>
        </ElTable>
      </div>

      <footer class="manage-table-footer">
        <ElPagination
          v-model:current-page="searchParams.current"
          v-model:page-size="searchParams.size"
          :total="total"
          :page-sizes="[10, 20, 30, 50]"
          layout="total, prev, pager, next, sizes"
          @current-change="handleCurrentChange"
          @size-change="handleSizeChange"
        />
      </footer>
    </ElCard>

    <ElDialog v-model="dialogVisible" :title="dialogTitle" width="560px" destroy-on-close>
      <p class="project-form-tip">
        {{ operateType === 'add' ? '项目创建后可继续维护成员、功能模块与测试环境。' : '项目标识创建后不可修改。' }}
      </p>
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="project-form-grid">
          <ElFormItem label="项目名称" prop="name">
            <ElInput v-model="form.name" placeholder="例如：支付结算平台" />
          </ElFormItem>
          <ElFormItem label="项目标识" prop="code">
            <ElInput
              v-model="form.code"
              placeholder="例如：PAYMENT"
              :disabled="operateType === 'edit'"
              @input="form.code = form.code.toUpperCase()"
            />
          </ElFormItem>
        </div>
        <ElFormItem label="负责人" prop="ownerId">
          <ElSelect
            v-model="form.ownerId"
            filterable
            class="w-full"
            :loading="ownerLoading"
            placeholder="选择项目负责人"
          >
            <ElOption
              v-for="item in ownerOptions"
              :key="item.id"
              :label="item.displayName || item.username"
              :value="item.id"
            >
              <span>{{ item.displayName || item.username }}</span>
              <span class="owner-option-username">@{{ item.username }}</span>
            </ElOption>
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="项目说明" prop="description">
          <ElInput v-model="form.description" type="textarea" :rows="3" maxlength="2000" show-word-limit />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">{{ submitButtonText }}</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.project-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.owner-option-username {
  float: right;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.table-status.is-pending > span {
  background: var(--el-color-warning);
}

.project-state-action {
  display: inline-flex;
}

@media (max-width: 620px) {
  .project-form-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
