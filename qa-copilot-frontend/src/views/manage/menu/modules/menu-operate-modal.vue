<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchCreateFastApiMenu, fetchUpdateFastApiMenu } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'MenuOperateModal' });

export type OperateType = UI.TableOperateType | 'addChild';

interface Props {
  operateType: OperateType;
  rowData?: Api.SystemManage.FastApiMenu | null;
  menuOptions: Api.SystemManage.FastApiMenu[];
}

const props = defineProps<Props>();

interface Emits {
  (e: 'submitted'): void;
}

const emit = defineEmits<Emits>();
const visible = defineModel<boolean>('visible', { default: false });
const submitting = ref(false);
const { formRef, validate, restoreValidation } = useForm();
const { defaultRequiredRule } = useFormRules();

const title = computed(() => {
  const titles: Record<OperateType, string> = {
    add: $t('page.manage.menu.addMenu'),
    addChild: $t('page.manage.menu.addChildMenu'),
    edit: $t('page.manage.menu.editMenu')
  };
  return titles[props.operateType];
});

type Model = Api.SystemManage.FastApiMenuCreateParams;

function createDefaultModel(): Model {
  return {
    parentId: null,
    routeName: '',
    path: '',
    component: '',
    title: '',
    icon: '',
    order: 0,
    menuType: 'page',
    permissionCode: null,
    enabled: true,
    hidden: false
  };
}

const model = ref(createDefaultModel());
const isButton = computed(() => model.value.menuType === 'button');

type RuleKey = Extract<keyof Model, 'title' | 'routeName' | 'path' | 'component' | 'permissionCode' | 'parentId'>;

const rules = computed<Partial<Record<RuleKey, App.Global.FormRule>>>(() => {
  const result: Partial<Record<RuleKey, App.Global.FormRule>> = {
    title: defaultRequiredRule,
    routeName: defaultRequiredRule
  };

  if (isButton.value) {
    result.parentId = defaultRequiredRule;
    result.permissionCode = defaultRequiredRule;
  } else {
    result.path = defaultRequiredRule;
    result.component = defaultRequiredRule;
  }

  return result;
});

const menuTypeOptions = computed(() => [
  { label: $t('page.manage.menu.type.directory'), value: 'directory' },
  { label: $t('page.manage.menu.type.menu'), value: 'page' },
  { label: $t('page.manage.menu.button'), value: 'button' }
]);

function getDescendantIds(menuId: number) {
  const result = new Set<number>();
  const pending = [menuId];

  while (pending.length) {
    const parentId = pending.pop();
    props.menuOptions.forEach(item => {
      if (item.parentId === parentId && !result.has(item.id)) {
        result.add(item.id);
        pending.push(item.id);
      }
    });
  }

  return result;
}

const parentOptions = computed(() => {
  const currentId = props.operateType === 'edit' ? props.rowData?.id : undefined;
  const excludedIds = currentId === undefined ? new Set<number>() : getDescendantIds(currentId);
  if (currentId !== undefined) excludedIds.add(currentId);

  return props.menuOptions.filter(item => {
    if (excludedIds.has(item.id) || item.menuType === 'button') return false;
    return !isButton.value || item.menuType === 'page';
  });
});

function handleInitModel() {
  model.value = createDefaultModel();

  if (props.operateType === 'addChild' && props.rowData) {
    model.value.parentId = props.rowData.id;
    model.value.menuType = props.rowData.menuType === 'page' ? 'button' : 'page';
  }

  if (props.operateType === 'edit' && props.rowData) {
    const { id: _id, createdAt: _createdAt, updatedAt: _updatedAt, ...data } = props.rowData;
    model.value = { ...data };
  }
}

function closeDrawer() {
  visible.value = false;
}

async function handleSubmit() {
  await validate();
  submitting.value = true;

  try {
    const form = model.value;
    const { error } =
      props.operateType === 'edit'
        ? await fetchUpdateFastApiMenu(props.rowData!.id, {
            parentId: form.parentId,
            path: form.path,
            component: form.component,
            title: form.title,
            icon: form.icon,
            order: form.order,
            menuType: form.menuType,
            permissionCode: form.permissionCode,
            enabled: form.enabled,
            hidden: form.hidden
          })
        : await fetchCreateFastApiMenu(form);
    if (error) return;

    window.$message?.success($t(props.operateType === 'edit' ? 'common.updateSuccess' : 'common.addSuccess'));
    closeDrawer();
    emit('submitted');
  } finally {
    submitting.value = false;
  }
}

watch(visible, () => {
  if (visible.value) {
    handleInitModel();
    restoreValidation();
  }
});

watch(
  () => model.value.menuType,
  menuType => {
    if (menuType === 'button') {
      model.value.path = '';
      model.value.component = '';
      model.value.hidden = true;
    } else {
      model.value.permissionCode = null;
    }

    if (model.value.parentId && !parentOptions.value.some(item => item.id === model.value.parentId)) {
      model.value.parentId = null;
    }
  }
);
</script>

<template>
  <ElDrawer
    v-model="visible"
    class="menu-editor-drawer"
    direction="rtl"
    size="520px"
    :show-close="false"
    :close-on-click-modal="!submitting"
  >
    <template #header>
      <div class="drawer-header">
        <div class="drawer-header__identity">
          <span class="drawer-header__icon" :class="[`is-${model.menuType}`]">
            <icon-material-symbols-folder-outline-rounded v-if="model.menuType === 'directory'" />
            <icon-material-symbols-description-outline-rounded v-else-if="model.menuType === 'page'" />
            <icon-material-symbols-touch-app-outline-rounded v-else />
          </span>
          <div>
            <h2>{{ title }}</h2>
            <span v-if="props.rowData" class="drawer-header__context">{{ props.rowData.routeName }}</span>
          </div>
        </div>
        <ElButton text circle class="drawer-close" :aria-label="$t('common.close')" @click="closeDrawer">
          <icon-material-symbols-close-rounded />
        </ElButton>
      </div>
    </template>

    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="menu-editor-form">
      <section class="form-section is-first">
        <div class="form-section__heading">
          <icon-material-symbols-tune-rounded />
          <span>{{ $t('page.manage.menu.basicInfo') }}</span>
        </div>

        <ElFormItem :label="$t('page.manage.menu.menuType')" prop="menuType">
          <ElSegmented v-model="model.menuType" :options="menuTypeOptions" block class="menu-type-segment" />
        </ElFormItem>

        <ElRow :gutter="16">
          <ElCol :sm="12" :xs="24">
            <ElFormItem :label="$t('page.manage.menu.menuName')" prop="title">
              <ElInput v-model="model.title" :placeholder="$t('page.manage.menu.form.menuName')" />
            </ElFormItem>
          </ElCol>
          <ElCol :sm="12" :xs="24">
            <ElFormItem :label="$t('page.manage.menu.parentId')" prop="parentId">
              <ElSelect
                v-model="model.parentId"
                clearable
                filterable
                class="w-full"
                :placeholder="$t('page.manage.menu.rootMenu')"
                :value-on-clear="() => null"
              >
                <ElOption
                  v-for="item in parentOptions"
                  :key="item.id"
                  :label="`${item.title} (${item.routeName})`"
                  :value="item.id"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>
      </section>

      <section class="form-section">
        <div class="form-section__heading">
          <icon-material-symbols-alt-route-rounded />
          <span>{{ $t('page.manage.menu.routeConfig') }}</span>
        </div>

        <ElFormItem :label="$t('page.manage.menu.routeName')" prop="routeName">
          <ElTooltip
            :disabled="props.operateType !== 'edit'"
            :content="$t('page.manage.menu.routeNameLocked')"
            placement="top-start"
          >
            <ElInput
              v-model="model.routeName"
              :disabled="props.operateType === 'edit'"
              :placeholder="$t('page.manage.menu.form.routeName')"
            />
          </ElTooltip>
        </ElFormItem>

        <Transition name="field-swap" mode="out-in">
          <div :key="model.menuType">
            <ElRow v-if="!isButton" :gutter="16">
              <ElCol :sm="12" :xs="24">
                <ElFormItem :label="$t('page.manage.menu.routePath')" prop="path">
                  <ElInput v-model="model.path" :placeholder="$t('page.manage.menu.form.routePath')" />
                </ElFormItem>
              </ElCol>
              <ElCol :sm="12" :xs="24">
                <ElFormItem :label="$t('page.manage.menu.page')" prop="component">
                  <ElInput v-model="model.component" :placeholder="$t('page.manage.menu.form.page')" />
                </ElFormItem>
              </ElCol>
            </ElRow>
            <ElFormItem v-else :label="$t('page.manage.menu.buttonCode')" prop="permissionCode">
              <ElInput v-model="model.permissionCode" :placeholder="$t('page.manage.menu.form.buttonCode')" />
            </ElFormItem>
          </div>
        </Transition>
      </section>

      <section class="form-section">
        <div class="form-section__heading">
          <icon-material-symbols-visibility-outline-rounded />
          <span>{{ $t('page.manage.menu.displaySettings') }}</span>
        </div>

        <ElRow :gutter="16">
          <ElCol :sm="16" :xs="24">
            <ElFormItem :label="$t('page.manage.menu.icon')" prop="icon">
              <ElInput v-model="model.icon" :placeholder="$t('page.manage.menu.form.icon')">
                <template #suffix>
                  <span class="icon-preview" :class="[`is-${model.menuType}`]">
                    <icon-material-symbols-folder-outline-rounded v-if="model.menuType === 'directory'" />
                    <icon-material-symbols-description-outline-rounded v-else-if="model.menuType === 'page'" />
                    <icon-material-symbols-touch-app-outline-rounded v-else />
                  </span>
                </template>
              </ElInput>
            </ElFormItem>
          </ElCol>
          <ElCol :sm="8" :xs="24">
            <ElFormItem :label="$t('page.manage.menu.order')" prop="order">
              <ElInputNumber v-model="model.order" :min="0" :max="9999" controls-position="right" class="w-full" />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <div class="switch-list">
          <div class="switch-row">
            <div class="switch-row__label">
              <icon-material-symbols-toggle-on-outline />
              <span>{{ $t('page.manage.menu.menuStatus') }}</span>
            </div>
            <ElSwitch v-model="model.enabled" />
          </div>
          <div class="switch-row">
            <div class="switch-row__label">
              <icon-material-symbols-visibility-off-outline-rounded />
              <span>{{ $t('page.manage.menu.hideInMenu') }}</span>
            </div>
            <ElSwitch v-model="model.hidden" :disabled="isButton" />
          </div>
        </div>
      </section>
    </ElForm>

    <template #footer>
      <div class="drawer-footer">
        <ElButton :disabled="submitting" @click="closeDrawer">{{ $t('common.cancel') }}</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">
          {{ $t('common.confirm') }}
        </ElButton>
      </div>
    </template>
  </ElDrawer>
</template>

<style lang="scss" scoped>
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.drawer-header__identity {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.drawer-header__identity h2 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 17px;
  font-weight: 650;
  line-height: 1.35;
  letter-spacing: 0;
}

.drawer-header__context {
  display: block;
  max-width: 320px;
  overflow: hidden;
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-header__icon,
.icon-preview {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
}

.drawer-header__icon {
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  background: rgb(var(--primary-color) / 11%);
  color: rgb(var(--primary-color));
  font-size: 20px;
}

.drawer-header__icon.is-directory,
.icon-preview.is-directory {
  background: rgb(var(--warning-color) / 12%);
  color: rgb(var(--warning-color));
}

.drawer-header__icon.is-button,
.icon-preview.is-button {
  background: rgb(var(--success-color) / 11%);
  color: rgb(var(--success-color));
}

.drawer-close {
  width: 32px;
  height: 32px;
  color: var(--el-text-color-secondary);
  font-size: 19px;
  transition:
    color 140ms ease-out,
    background-color 140ms ease-out,
    transform 100ms ease-out;
}

.drawer-close:hover {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.drawer-close:active {
  transform: scale(0.94);
}

.menu-editor-form {
  padding: 0 20px 16px;
}

.form-section {
  padding: 22px 0 4px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.form-section.is-first {
  padding-top: 8px;
  border-top: 0;
}

.form-section__heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.4;
}

.form-section__heading > :first-child {
  color: var(--el-text-color-secondary);
  font-size: 17px;
}

.menu-type-segment {
  width: 100%;
}

.icon-preview {
  width: 24px;
  height: 24px;
  background: rgb(var(--primary-color) / 10%);
  color: rgb(var(--primary-color));
  font-size: 15px;
}

.switch-list {
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 48px;
  padding: 0 14px;
  background: var(--el-bg-color);
}

.switch-row + .switch-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

.switch-row__label {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--el-text-color-regular);
}

.switch-row__label > :first-child {
  color: var(--el-text-color-secondary);
  font-size: 18px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.drawer-footer :deep(.el-button) {
  min-width: 88px;
}

.field-swap-enter-active,
.field-swap-leave-active {
  transition:
    opacity 160ms ease-out,
    transform 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.field-swap-enter-from,
.field-swap-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

:global(.menu-editor-drawer) {
  max-width: 100vw;
  box-shadow: -18px 0 48px rgb(0 0 0 / 10%);
}

:global(.menu-editor-drawer .el-drawer__header) {
  margin: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: color-mix(in srgb, var(--el-bg-color) 88%, transparent);
  padding: 14px 18px;
  backdrop-filter: blur(18px) saturate(150%);
}

:global(.menu-editor-drawer .el-drawer__body) {
  padding: 0;
}

:global(.menu-editor-drawer .el-drawer__footer) {
  border-top: 1px solid var(--el-border-color-lighter);
  background: color-mix(in srgb, var(--el-bg-color) 90%, transparent);
  padding: 12px 18px;
  backdrop-filter: blur(18px) saturate(150%);
}

:global(.menu-editor-drawer .el-form-item__label) {
  padding-bottom: 7px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  font-weight: 550;
}

@media (max-width: 560px) {
  :global(.menu-editor-drawer) {
    width: 100% !important;
  }

  .menu-editor-form {
    padding-right: 16px;
    padding-left: 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-close,
  .field-swap-enter-active,
  .field-swap-leave-active {
    transition-duration: 0.01ms !important;
    transform: none !important;
  }
}

@media (prefers-reduced-transparency: reduce) {
  :global(.menu-editor-drawer .el-drawer__header),
  :global(.menu-editor-drawer .el-drawer__footer) {
    background: var(--el-bg-color);
    backdrop-filter: none;
  }
}

@media (prefers-contrast: more) {
  .switch-list,
  .form-section {
    border-color: var(--el-text-color-primary);
  }
}
</style>
