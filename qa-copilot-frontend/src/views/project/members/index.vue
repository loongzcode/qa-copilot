<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import dayjs from 'dayjs';
import {
  fetchCreateProjectMember,
  fetchDeleteProjectMember,
  fetchGetProjectList,
  fetchGetProjectMemberList,
  fetchGetProjectMemberOptions,
  fetchUpdateProjectMember
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'ProjectMembers' });

type MemberRole = Api.ProjectManage.ProjectMemberRole;
type MemberForm = {
  userId: number | null;
  memberRole: MemberRole;
};

const authStore = useAuthStore();
const loading = ref(false);
const projectLoading = ref(false);
const userLoading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const operateType = ref<'add' | 'edit'>('add');
const editingUserId = ref<number | null>(null);
const editingUserLabel = ref('');
const activeProjectId = ref<number | null>(null);
const projects = ref<Api.ProjectManage.Project[]>([]);
const records = ref<Api.ProjectManage.ProjectMember[]>([]);
const userOptions = ref<Api.ProjectManage.ProjectMemberOption[]>([]);
const total = ref(0);
const formRef = ref<FormInstance>();

const searchParams = reactive<Api.ProjectManage.ProjectMemberSearchParams>({
  current: 1,
  size: 10,
  keyword: ''
});

const form = reactive<MemberForm>({
  userId: null,
  memberRole: 'MEMBER'
});

const roleOptions: Array<{ label: string; value: MemberRole; description: string }> = [
  { label: '负责人', value: 'OWNER', description: '拥有项目全部权限' },
  { label: '管理员', value: 'MANAGER', description: '维护成员、模块与环境' },
  { label: '成员', value: 'MEMBER', description: '维护测试资产并执行任务' },
  { label: '访客', value: 'VIEWER', description: '仅查看项目内容' }
];

const editableRoleOptions = roleOptions.filter(item => item.value !== 'OWNER');

const rules: FormRules<MemberForm> = {
  userId: [{ required: true, message: '请选择系统用户', trigger: 'change' }],
  memberRole: [{ required: true, message: '请选择项目角色', trigger: 'change' }]
};

const canManageMembers = computed(() => {
  const buttons = authStore.userInfo.buttons;
  return buttons.includes('*') || buttons.includes('project:member:manage');
});

const activeProject = computed(() => projects.value.find(item => item.id === activeProjectId.value));
const isArchivedProject = computed(() => activeProject.value?.status === 'ARCHIVED');
const dialogTitle = computed(() => (operateType.value === 'add' ? '添加项目成员' : '编辑成员角色'));

function roleLabel(role: MemberRole) {
  return roleOptions.find(item => item.value === role)?.label || role;
}

function roleDescription(role: MemberRole) {
  return roleOptions.find(item => item.value === role)?.description || '-';
}

function roleTagType(role: MemberRole) {
  return ({ OWNER: 'danger', MANAGER: 'warning', MEMBER: 'primary', VIEWER: 'info' } as const)[role];
}

function userLabel(user: Api.ProjectManage.ProjectMemberOption) {
  return user.displayName || user.username;
}

async function getProjects() {
  projectLoading.value = true;
  const { data, error } = await fetchGetProjectList({
    current: 1,
    size: 200,
    keyword: ''
  });
  projectLoading.value = false;

  if (error) return;

  projects.value = data.records;
  if (!activeProjectId.value || !projects.value.some(item => item.id === activeProjectId.value)) {
    activeProjectId.value = projects.value[0]?.id ?? null;
  }
}

async function getData() {
  if (!activeProjectId.value) {
    records.value = [];
    total.value = 0;
    return;
  }

  loading.value = true;
  const { data, error } = await fetchGetProjectMemberList(activeProjectId.value, {
    ...searchParams,
    keyword: searchParams.keyword.trim()
  });
  loading.value = false;

  if (error) return;

  records.value = data.records;
  total.value = data.total;
}

async function handleProjectChange() {
  searchParams.current = 1;
  searchParams.keyword = '';
  userOptions.value = [];
  await getData();
}

async function handleSearch() {
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

async function getUserOptions(keyword = '') {
  if (!activeProjectId.value) return;

  userLoading.value = true;
  const { data, error } = await fetchGetProjectMemberOptions(activeProjectId.value, {
    keyword: keyword.trim(),
    limit: 20
  });
  userLoading.value = false;

  if (!error) userOptions.value = data;
}

async function handleAdd() {
  if (!activeProjectId.value) {
    window.$message?.warning('请先选择项目');
    return;
  }
  if (isArchivedProject.value) {
    window.$message?.warning('已归档项目不能管理成员');
    return;
  }
  operateType.value = 'add';
  editingUserId.value = null;
  editingUserLabel.value = '';
  Object.assign(form, { userId: null, memberRole: 'MEMBER' });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
  await getUserOptions();
}

function handleEdit(row: Api.ProjectManage.ProjectMember) {
  operateType.value = 'edit';
  editingUserId.value = row.userId;
  editingUserLabel.value = `${row.displayName || row.username} (@${row.username})`;
  Object.assign(form, {
    userId: row.userId,
    memberRole: row.memberRole
  });
  formRef.value?.clearValidate();
  dialogVisible.value = true;
}

async function submitForm() {
  await formRef.value?.validate();
  if (!activeProjectId.value || !form.userId) return;

  submitting.value = true;
  const { error } =
    operateType.value === 'add'
      ? await fetchCreateProjectMember(activeProjectId.value, {
          userId: form.userId,
          memberRole: form.memberRole
        })
      : await fetchUpdateProjectMember(activeProjectId.value, editingUserId.value!, {
          memberRole: form.memberRole
        });
  submitting.value = false;

  if (error) return;

  dialogVisible.value = false;
  window.$message?.success(operateType.value === 'add' ? '成员添加成功' : '成员角色修改成功');
  await Promise.all([getData(), getProjects()]);
}

async function removeMember(row: Api.ProjectManage.ProjectMember) {
  if (!activeProjectId.value) return;

  const { error } = await fetchDeleteProjectMember(activeProjectId.value, row.userId);
  if (error) return;

  window.$message?.success('成员已移除');
  if (records.value.length === 1 && searchParams.current > 1) searchParams.current -= 1;
  await Promise.all([getData(), getProjects()]);
}

async function initialize() {
  await getProjects();
  await getData();
}

initialize();
</script>

<template>
  <div class="project-page manage-table-page">
    <ElCard class="project-card manage-table-card">
      <template #header>
        <div class="project-page-header">
          <div class="project-page-title">
            <h2>项目成员</h2>
            <p>维护项目成员及 OWNER、MANAGER、MEMBER、VIEWER 四级角色</p>
          </div>
          <div class="project-page-actions">
            <ElTooltip content="刷新" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <icon-mdi-refresh :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <ElButton
              v-if="canManageMembers"
              type="primary"
              :disabled="!activeProjectId || isArchivedProject"
              @click="handleAdd"
            >
              <template #icon><icon-ic-round-plus /></template>
              添加成员
            </ElButton>
          </div>
        </div>
      </template>

      <div class="project-toolbar">
        <ElSelect
          v-model="activeProjectId"
          class="project-selector"
          :loading="projectLoading"
          placeholder="选择项目"
          @change="handleProjectChange"
        >
          <ElOption v-for="item in projects" :key="item.id" :label="item.name" :value="item.id">
            <span>{{ item.name }}</span>
            <span class="project-option-code">{{ item.code }}</span>
          </ElOption>
        </ElSelect>
        <ElInput
          v-model="searchParams.keyword"
          clearable
          class="project-search"
          placeholder="搜索成员姓名或用户名"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElButton type="primary" plain :disabled="!activeProjectId" @click="handleSearch">查询</ElButton>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="records" row-key="userId">
          <ElTableColumn label="成员" min-width="220">
            <template #default="{ row }: { row: Api.ProjectManage.ProjectMember }">
              <div class="project-name-cell">
                <ElAvatar :size="34">{{ (row.displayName || row.username).slice(0, 1) }}</ElAvatar>
                <span class="project-name-copy">
                  <strong>{{ row.displayName || row.username }}</strong>
                  <small>@{{ row.username }}</small>
                </span>
              </div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="项目角色" width="140">
            <template #default="{ row }: { row: Api.ProjectManage.ProjectMember }">
              <ElTag :type="roleTagType(row.memberRole)" effect="plain" size="small">
                {{ roleLabel(row.memberRole) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="权限说明" min-width="260">
            <template #default="{ row }: { row: Api.ProjectManage.ProjectMember }">
              <span class="project-secondary">{{ roleDescription(row.memberRole) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="加入时间" min-width="160">
            <template #default="{ row }: { row: Api.ProjectManage.ProjectMember }">
              <span class="table-date">{{ dayjs(row.createdAt).format('YYYY-MM-DD HH:mm') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn v-if="canManageMembers" label="操作" width="112" align="right" fixed="right">
            <template #default="{ row }: { row: Api.ProjectManage.ProjectMember }">
              <div class="table-row-actions">
                <ElTooltip :content="row.memberRole === 'OWNER' ? '负责人角色不可修改' : '编辑角色'" placement="top">
                  <span>
                    <ElButton
                      text
                      circle
                      class="table-row-action"
                      :disabled="row.memberRole === 'OWNER' || isArchivedProject"
                      @click="handleEdit(row)"
                    >
                      <icon-material-symbols-edit-outline-rounded />
                    </ElButton>
                  </span>
                </ElTooltip>
                <ElPopconfirm
                  title="确认从项目中移除该成员？"
                  confirm-button-text="确认移除"
                  cancel-button-text="取消"
                  @confirm="removeMember(row)"
                >
                  <template #reference>
                    <span>
                      <ElButton
                        text
                        circle
                        class="table-row-action is-danger"
                        :disabled="row.memberRole === 'OWNER' || isArchivedProject"
                      >
                        <icon-ic-round-delete />
                      </ElButton>
                    </span>
                  </template>
                </ElPopconfirm>
              </div>
            </template>
          </ElTableColumn>
          <template #empty><ElEmpty description="当前项目暂无成员" :image-size="72" /></template>
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

    <ElDialog v-model="dialogVisible" :title="dialogTitle" width="500px" destroy-on-close>
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="系统用户" prop="userId">
          <ElInput v-if="operateType === 'edit'" :model-value="editingUserLabel" disabled />
          <ElSelect
            v-else
            v-model="form.userId"
            filterable
            remote
            class="w-full"
            :loading="userLoading"
            placeholder="选择要加入项目的用户"
            :remote-method="getUserOptions"
          >
            <ElOption v-for="item in userOptions" :key="item.userId" :label="userLabel(item)" :value="item.userId">
              <span>{{ userLabel(item) }}</span>
              <span class="member-option-username">@{{ item.username }}</span>
            </ElOption>
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="项目角色" prop="memberRole">
          <ElRadioGroup v-model="form.memberRole" class="role-radio-group">
            <ElRadio v-for="item in editableRoleOptions" :key="item.value" :value="item.value" border>
              {{ item.label }}
            </ElRadio>
          </ElRadioGroup>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitForm">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style src="../../manage/components/manage-table.scss" lang="scss"></style>

<style src="../shared.scss" lang="scss"></style>

<style scoped lang="scss">
.project-option-code,
.member-option-username {
  float: right;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.role-radio-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  width: 100%;
  gap: 10px;
}

.role-radio-group :deep(.el-radio) {
  margin: 0;
}

@media (max-width: 620px) {
  .role-radio-group {
    grid-template-columns: 1fr;
  }
}
</style>
