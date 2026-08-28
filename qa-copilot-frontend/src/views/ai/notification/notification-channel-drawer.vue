<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchCreateNotificationChannel, fetchUpdateNotificationChannel } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';

defineOptions({ name: 'NotificationChannelDrawer' });

interface Props {
  operateType: UI.TableOperateType;
  rowData?: Api.AIManage.NotificationChannel | null;
}

type FormModel = {
  name: string;
  channelType: Api.AIManage.NotificationChannelType;
  secret: string;
  timeoutSeconds: number;
  host: string;
  port: number;
  security: 'NONE' | 'STARTTLS' | 'SSL';
  username: string;
  fromEmail: string;
  recipientsText: string;
  subjectPrefix: string;
  enabled: boolean;
  importanceThreshold: number;
  breakingOnly: boolean;
};

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'submitted'): void }>();
const visible = defineModel<boolean>('visible', { default: false });
const { formRef, validate, restoreValidation } = useForm();
const { defaultRequiredRule } = useFormRules();
const submitting = ref(false);
const model = ref(createDefaultModel());

const isSmtp = computed(() => model.value.channelType === 'SMTP');
const title = computed(() => (props.operateType === 'add' ? '新增通知渠道' : '编辑通知渠道'));
const secretLabel = computed(() => (isSmtp.value ? '邮箱密码或授权码' : 'Webhook 地址'));
const secretPlaceholder = computed(() => {
  if (props.operateType === 'edit') return '留空表示继续使用已保存的密钥';
  if (isSmtp.value) return '填写邮箱密码或客户端授权码';
  return '填写完整 HTTPS 地址，地址中的访问令牌会被加密';
});

const channelTypeOptions: Array<{ value: Api.AIManage.NotificationChannelType; label: string }> = [
  { value: 'WEBHOOK', label: '通用 Webhook' },
  { value: 'WECHAT_WORK_BOT', label: '企业微信群机器人' },
  { value: 'DINGTALK_BOT', label: '钉钉群机器人' },
  { value: 'SMTP', label: 'SMTP 邮件' }
];

const rules = {
  name: defaultRequiredRule,
  secret: {
    trigger: 'blur',
    validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
      callback(props.operateType === 'add' && !value.trim() ? new Error(`请填写${secretLabel.value}`) : undefined);
    }
  }
};

function createDefaultModel(): FormModel {
  return {
    name: '',
    channelType: 'WEBHOOK',
    secret: '',
    timeoutSeconds: 10,
    host: '',
    port: 587,
    security: 'STARTTLS',
    username: '',
    fromEmail: '',
    recipientsText: '',
    subjectPrefix: '[QA Copilot]',
    enabled: true,
    importanceThreshold: 80,
    breakingOnly: false
  };
}

function initModel() {
  const next = createDefaultModel();
  if (props.operateType === 'edit' && props.rowData) {
    const { config } = props.rowData;
    Object.assign(next, {
      name: props.rowData.name,
      channelType: props.rowData.channelType,
      timeoutSeconds: config.timeoutSeconds ?? 10,
      host: config.host ?? '',
      port: config.port ?? 587,
      security: config.security ?? 'STARTTLS',
      username: config.username ?? '',
      fromEmail: config.fromEmail ?? '',
      recipientsText: (config.recipients ?? []).join('\n'),
      subjectPrefix: config.subjectPrefix ?? '[QA Copilot]',
      enabled: props.rowData.enabled,
      importanceThreshold: props.rowData.importanceThreshold,
      breakingOnly: props.rowData.breakingOnly
    });
  }
  model.value = next;
}

function handleChannelTypeChange(type: Api.AIManage.NotificationChannelType) {
  model.value.secret = '';
  if (type === 'SMTP' && model.value.port === 587) return;
  model.value.port = type === 'SMTP' ? 587 : model.value.port;
}

function buildConfig(): Api.AIManage.NotificationChannelConfig {
  if (!isSmtp.value) return { timeoutSeconds: model.value.timeoutSeconds };
  return {
    timeoutSeconds: model.value.timeoutSeconds,
    host: model.value.host.trim(),
    port: model.value.port,
    security: model.value.security,
    username: model.value.username.trim(),
    fromEmail: model.value.fromEmail.trim(),
    recipients: model.value.recipientsText
      .split(/[\n,;]/)
      .map(item => item.trim())
      .filter(Boolean),
    subjectPrefix: model.value.subjectPrefix.trim() || '[QA Copilot]'
  };
}

async function handleSubmit() {
  await validate();
  submitting.value = true;
  const payload: Api.AIManage.NotificationChannelCreateParams = {
    name: model.value.name.trim(),
    channelType: model.value.channelType,
    config: buildConfig(),
    secret: model.value.secret.trim(),
    enabled: model.value.enabled,
    importanceThreshold: model.value.importanceThreshold,
    breakingOnly: model.value.breakingOnly
  };
  const result =
    props.operateType === 'add'
      ? await fetchCreateNotificationChannel(payload)
      : await fetchUpdateNotificationChannel(props.rowData!.id, {
          ...payload,
          secret: payload.secret || undefined
        });
  submitting.value = false;
  if (result.error) return;
  window.$message?.success(props.operateType === 'add' ? '通知渠道已创建' : '通知渠道已更新');
  visible.value = false;
  emit('submitted');
}

watch(visible, value => {
  if (!value) return;
  initModel();
  restoreValidation();
});
</script>

<template>
  <ElDrawer v-model="visible" :size="560" class="notification-channel-drawer">
    <template #header>
      <div class="notification-drawer-heading">
        <span><SvgIcon icon="mdi:bell-cog-outline" /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>自动化任务结束后，按规则发送结果摘要</small>
        </div>
      </div>
    </template>

    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="notification-form">
      <section>
        <h3>基本信息</h3>
        <ElFormItem label="渠道名称" prop="name">
          <ElInput v-model="model.name" maxlength="100" placeholder="例如：测试团队告警群" />
        </ElFormItem>
        <ElFormItem label="渠道类型" prop="channelType">
          <ElSelect v-model="model.channelType" class="w-full" @change="handleChannelTypeChange">
            <ElOption v-for="item in channelTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem :label="secretLabel" prop="secret">
          <ElInput
            v-model="model.secret"
            type="password"
            show-password-on="click"
            autocomplete="new-password"
            :placeholder="secretPlaceholder"
          />
          <p v-if="props.operateType === 'edit' && props.rowData?.secretConfigured" class="notification-form-hint">
            当前密钥已配置；查询接口不会把原文返回浏览器。
          </p>
        </ElFormItem>
      </section>

      <section v-if="isSmtp">
        <h3>邮件服务器配置</h3>
        <div class="notification-form-grid">
          <ElFormItem label="SMTP 服务器">
            <ElInput v-model="model.host" placeholder="smtp.example.com" />
          </ElFormItem>
          <ElFormItem label="端口">
            <ElInputNumber v-model="model.port" :min="1" :max="65535" controls-position="right" class="w-full" />
          </ElFormItem>
          <ElFormItem label="传输安全">
            <ElSelect v-model="model.security" class="w-full">
              <ElOption label="STARTTLS（推荐）" value="STARTTLS" />
              <ElOption label="SSL/TLS" value="SSL" />
              <ElOption label="不加密" value="NONE" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="登录账号（可选）">
            <ElInput v-model="model.username" autocomplete="off" />
          </ElFormItem>
          <ElFormItem label="发件人邮箱">
            <ElInput v-model="model.fromEmail" placeholder="qa@example.com" />
          </ElFormItem>
          <ElFormItem label="主题前缀">
            <ElInput v-model="model.subjectPrefix" maxlength="100" />
          </ElFormItem>
        </div>
        <ElFormItem label="收件人邮箱">
          <ElInput v-model="model.recipientsText" type="textarea" :rows="3" placeholder="每行填写一个邮箱" />
        </ElFormItem>
      </section>

      <section>
        <h3>发送规则</h3>
        <div class="notification-form-grid">
          <ElFormItem label="最低重要度">
            <ElSelect v-model="model.importanceThreshold" class="w-full">
              <ElOption label="所有结果（通过、取消、失败）" :value="60" />
              <ElOption label="取消及失败" :value="80" />
              <ElOption label="仅失败或超时" :value="100" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="请求超时">
            <ElInputNumber v-model="model.timeoutSeconds" :min="1" :max="60" controls-position="right" class="w-full" />
          </ElFormItem>
        </div>
        <div class="notification-switch-row">
          <div>
            <strong>只发送阻断性结果</strong>
            <small>只通知失败和超时，优先级高于最低重要度</small>
          </div>
          <ElSwitch v-model="model.breakingOnly" />
        </div>
        <div class="notification-switch-row">
          <div>
            <strong>启用渠道</strong>
            <small>停用后保留配置，但后台不会继续发送</small>
          </div>
          <ElSwitch v-model="model.enabled" />
        </div>
      </section>
    </ElForm>

    <template #footer>
      <ElButton @click="visible = false">取消</ElButton>
      <ElButton type="primary" :loading="submitting" @click="handleSubmit">保存</ElButton>
    </template>
  </ElDrawer>
</template>

<style lang="scss">
.notification-channel-drawer .el-drawer__header {
  margin-bottom: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 18px 20px;
}

.notification-channel-drawer .el-drawer__body {
  padding: 0;
}
.notification-channel-drawer .el-drawer__footer {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 20px;
}

.notification-drawer-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}
.notification-drawer-heading > span {
  display: inline-flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 19px;
}
.notification-drawer-heading strong,
.notification-drawer-heading small {
  display: block;
}
.notification-drawer-heading strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}
.notification-drawer-heading small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.notification-form section {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 20px;
}
.notification-form section:last-child {
  border-bottom: 0;
}
.notification-form h3 {
  margin: 0 0 18px;
  color: var(--el-text-color-primary);
  font-size: 13px;
}
.notification-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.notification-form-hint {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.notification-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
}
.notification-switch-row + .notification-switch-row {
  margin-top: 10px;
}
.notification-switch-row strong,
.notification-switch-row small {
  display: block;
}
.notification-switch-row strong {
  font-size: 13px;
  font-weight: 550;
}
.notification-switch-row small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 600px) {
  .notification-channel-drawer {
    width: 100% !important;
  }
  .notification-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
