<script setup lang="ts">
import { computed, ref } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'PwdLogin' });

const authStore = useAuthStore();
const { formRef, validate } = useForm();

interface FormModel {
  userName: string;
  password: string;
}

const model = ref<FormModel>({
  userName: '',
  password: ''
});

const rules = computed<Record<keyof FormModel, App.Global.FormRule[]>>(() => {
  // inside computed to make locale ref, if not apply i18n, you can define it without computed
  const { formRules } = useFormRules();

  return {
    userName: formRules.userName,
    password: formRules.pwd
  };
});

async function handleSubmit() {
  await validate();
  await authStore.login(model.value.userName, model.value.password);
}
</script>

<template>
  <ElForm
    ref="formRef"
    class="knowledge-login-form"
    :model="model"
    :rules="rules"
    size="large"
    label-position="top"
    @keyup.enter="handleSubmit"
  >
    <ElFormItem prop="userName">
      <template #label>用户名</template>
      <ElInput
        v-model="model.userName"
        autocomplete="username"
        :placeholder="$t('page.login.common.userNamePlaceholder')"
      >
        <template #prefix><SvgIcon icon="mdi:account-outline" /></template>
      </ElInput>
    </ElFormItem>
    <ElFormItem prop="password">
      <template #label>密码</template>
      <ElInput
        v-model="model.password"
        type="password"
        autocomplete="current-password"
        show-password-on="click"
        :placeholder="$t('page.login.common.passwordPlaceholder')"
      >
        <template #prefix><SvgIcon icon="mdi:lock-outline" /></template>
      </ElInput>
    </ElFormItem>
    <div class="login-options">
      <ElCheckbox>{{ $t('page.login.pwdLogin.rememberMe') }}</ElCheckbox>
      <span>如需重置密码，请联系管理员</span>
    </div>
    <ElButton class="login-submit" type="primary" size="large" :loading="authStore.loginLoading" @click="handleSubmit">
      <span>进入 QA 工作台</span>
      <SvgIcon v-if="!authStore.loginLoading" icon="mdi:arrow-right" />
    </ElButton>
  </ElForm>
</template>

<style scoped>
.knowledge-login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.knowledge-login-form :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 8px;
  color: var(--login-ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.knowledge-login-form :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--login-line) inset;
  transition:
    box-shadow 160ms ease,
    background-color 160ms ease;
}

.knowledge-login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgb(23 109 84 / 24%) inset;
}

.login-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 2px 0 20px;
  color: var(--login-muted);
  font-size: 12px;
}

.login-submit {
  width: 100%;
  height: 48px;
  border: 0;
  border-radius: 12px;
  font-weight: 650;
  background: #176d54;
  box-shadow: 0 10px 24px rgb(23 109 84 / 20%);
  transition:
    transform 140ms cubic-bezier(0.23, 1, 0.32, 1),
    box-shadow 160ms ease,
    background-color 160ms ease;
}

.login-submit :deep(span) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
}

.login-submit:active {
  transform: scale(0.98);
}

@media (hover: hover) and (pointer: fine) {
  .login-submit:hover {
    background: #125e48;
    box-shadow: 0 12px 28px rgb(23 109 84 / 26%);
  }
}

@media (max-width: 480px) {
  .login-options {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
