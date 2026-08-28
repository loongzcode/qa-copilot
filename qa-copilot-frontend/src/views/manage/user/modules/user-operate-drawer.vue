<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchCreateFastApiUser, fetchGetFastApiRoleOptions, fetchUpdateFastApiUser } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'UserOperateDrawer' });

interface Props {
  operateType: UI.TableOperateType;
  rowData?: Api.SystemManage.FastApiUser | null;
}

const props = defineProps<Props>();

interface Emits {
  (e: 'submitted'): void;
}

const emit = defineEmits<Emits>();

const visible = defineModel<boolean>('visible', {
  default: false
});

const { formRef, validate, restoreValidation } = useForm();
const { defaultRequiredRule } = useFormRules();

type Model = {
  username: string;
  displayName: string;
  password: string;
  isActive: boolean;
  roleIds: number[];
};

const model = ref(createDefaultModel());

function createDefaultModel(): Model {
  return {
    username: '',
    displayName: '',
    password: '',
    isActive: true,
    roleIds: []
  };
}

const roleOptions = ref<Api.SystemManage.FastApiRoleOption[]>([]);
const roleLoading = ref(false);
const submitting = ref(false);

async function getRoleOptions() {
  roleLoading.value = true;
  const { data, error } = await fetchGetFastApiRoleOptions();
  roleLoading.value = false;

  if (!error) {
    roleOptions.value = data;
  }
}

const title = computed(() =>
  props.operateType === 'add' ? $t('page.manage.user.addUser') : $t('page.manage.user.editUser')
);

type RuleKey = Extract<keyof Model, 'username' | 'displayName' | 'password'>;

const rules = computed<Partial<Record<RuleKey, App.Global.FormRule>>>(() => {
  const base: Partial<Record<RuleKey, App.Global.FormRule>> = {
    username: defaultRequiredRule,
    displayName: defaultRequiredRule
  };

  if (props.operateType === 'add') {
    base.password = defaultRequiredRule;
  }

  return base;
});

function handleInitModel() {
  model.value = createDefaultModel();
  if (props.operateType === 'edit' && props.rowData) {
    model.value.username = props.rowData.username;
    model.value.displayName = props.rowData.displayName;
    model.value.isActive = props.rowData.isActive;
    model.value.roleIds = [...props.rowData.roleIds];
  }
}

function closeDrawer() {
  visible.value = false;
}

async function handleSubmit() {
  await validate();
  submitting.value = true;

  const form = model.value;
  const { error } =
    props.operateType === 'add'
      ? await fetchCreateFastApiUser(form)
      : await fetchUpdateFastApiUser(props.rowData!.id, {
          displayName: form.displayName,
          password: form.password || undefined,
          isActive: form.isActive,
          roleIds: form.roleIds
        });
  submitting.value = false;
  if (error) return;

  window.$message?.success($t(props.operateType === 'add' ? 'common.addSuccess' : 'common.updateSuccess'));
  closeDrawer();
  emit('submitted');
}

watch(visible, () => {
  if (visible.value) {
    handleInitModel();
    restoreValidation();
    getRoleOptions();
  }
});
</script>

<template>
  <ElDrawer v-model="visible" :size="480" class="manage-operate-drawer">
    <template #header>
      <div class="operate-drawer-heading">
        <span class="operate-drawer-icon"><icon-material-symbols-person-outline-rounded /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>{{ $t('page.manage.common.basicInfo') }}</small>
        </div>
      </div>
    </template>
    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="operate-form">
      <ElFormItem :label="$t('page.manage.user.userName')" prop="username">
        <ElInput
          v-model="model.username"
          :placeholder="$t('page.manage.user.form.userName')"
          :disabled="props.operateType === 'edit'"
        />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.user.nickName')" prop="displayName">
        <ElInput v-model="model.displayName" :placeholder="$t('page.manage.user.form.nickName')" />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.user.password')" prop="password">
        <ElInput
          v-model="model.password"
          type="password"
          show-password-on="click"
          autocomplete="new-password"
          :placeholder="$t('page.manage.user.password')"
        />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.user.userRole')" prop="roleIds">
        <ElSelect
          v-model="model.roleIds"
          multiple
          filterable
          clearable
          :loading="roleLoading"
          :placeholder="$t('page.manage.user.form.userRole')"
        >
          <ElOption
            v-for="role in roleOptions"
            :key="role.id"
            :label="role.name + ' (' + role.code + ')'"
            :value="role.id"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.user.userStatus')" prop="isActive">
        <ElSwitch v-model="model.isActive" />
      </ElFormItem>
    </ElForm>
    <template #footer>
      <ElSpace :size="16">
        <ElButton @click="closeDrawer">{{ $t('common.cancel') }}</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">{{ $t('common.confirm') }}</ElButton>
      </ElSpace>
    </template>
  </ElDrawer>
</template>

<style lang="scss">
.manage-operate-drawer .el-drawer__header {
  margin-bottom: 0;
  padding: 18px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.manage-operate-drawer .el-drawer__body {
  padding: 20px;
}
.manage-operate-drawer .el-drawer__footer {
  padding: 12px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.operate-drawer-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}
.operate-drawer-heading strong {
  display: block;
  color: var(--el-text-color-primary);
  font-size: 16px;
}
.operate-drawer-heading small {
  display: block;
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.operate-drawer-icon {
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
.operate-form .el-form-item {
  margin-bottom: 18px;
}
</style>
