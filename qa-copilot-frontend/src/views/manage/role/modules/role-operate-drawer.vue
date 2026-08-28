<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { fetchCreateFastApiRole, fetchGetFastApiMenuList, fetchUpdateFastApiRole } from '@/service/api';
import { useForm, useFormRules } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({ name: 'RoleOperateDrawer' });

interface Props {
  /** the type of operation */
  operateType: UI.TableOperateType;
  /** the edit row data */
  rowData?: Api.SystemManage.FastApiRole | null;
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

const title = computed(() => {
  const titles: Record<UI.TableOperateType, string> = {
    add: $t('page.manage.role.addRole'),
    edit: $t('page.manage.role.editRole')
  };
  return titles[props.operateType];
});

type Model = Api.SystemManage.FastApiRoleCreateParams;

type MenuTreeNode = Api.SystemManage.FastApiMenu & {
  label: string;
  children: MenuTreeNode[];
};

type MenuTreeInstance = {
  getCheckedKeys: (leafOnly?: boolean) => Array<number | string>;
  getHalfCheckedKeys: () => Array<number | string>;
  setCheckedKeys: (keys: number[]) => void;
};

const model = ref(createDefaultModel());
const submitting = ref(false);
const menuLoading = ref(false);
const menus = ref<Api.SystemManage.FastApiMenu[]>([]);
const menuTreeRef = ref<MenuTreeInstance | null>(null);

const menuTree = computed<MenuTreeNode[]>(() => {
  const nodes = new Map<number, MenuTreeNode>();

  [...menus.value]
    .sort((left, right) => left.order - right.order || left.id - right.id)
    .forEach(menu => {
      nodes.set(menu.id, {
        ...menu,
        label: menu.title,
        children: []
      });
    });

  const roots: MenuTreeNode[] = [];
  nodes.forEach(node => {
    const parent = node.parentId === null ? undefined : nodes.get(node.parentId);
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
});

const selectedMenuCount = computed(() => model.value.menuIds.length);

function createDefaultModel(): Model {
  return {
    code: '',
    name: '',
    description: '',
    enabled: true,
    menuIds: []
  };
}

type RuleKey = Extract<keyof Model, 'code' | 'name'>;

const rules: Record<RuleKey, App.Global.FormRule> = {
  code: defaultRequiredRule,
  name: defaultRequiredRule
};

function handleInitModel() {
  model.value = createDefaultModel();

  if (props.operateType === 'edit' && props.rowData) {
    model.value = {
      code: props.rowData.code,
      name: props.rowData.name,
      description: props.rowData.description,
      enabled: props.rowData.enabled,
      menuIds: [...props.rowData.menuIds]
    };
  }
}

function closeDrawer() {
  visible.value = false;
}

async function loadMenus() {
  menuLoading.value = true;
  const { data, error } = await fetchGetFastApiMenuList();
  menuLoading.value = false;

  if (!error) {
    menus.value = data;
  }
}

function syncMenuIds() {
  if (!menuTreeRef.value) return;

  // Element Plus 会把只选中一部分子节点的父节点标记为“半选”。
  // 父级菜单也需要保存，否则后端构建菜单树时可能缺少目录或页面节点。
  const checkedKeys = menuTreeRef.value.getCheckedKeys(false);
  const halfCheckedKeys = menuTreeRef.value.getHalfCheckedKeys();
  model.value.menuIds = [...new Set([...checkedKeys, ...halfCheckedKeys].map(Number))];
}

function getMenuRestoreKeys(menuIds: number[]) {
  const selectedIds = new Set(menuIds);
  const childrenByParent = new Map<number, number[]>();

  menus.value.forEach(menu => {
    if (menu.parentId === null) return;

    const children = childrenByParent.get(menu.parentId) ?? [];
    children.push(menu.id);
    childrenByParent.set(menu.parentId, children);
  });

  function isWholeBranchSelected(menuId: number): boolean {
    if (!selectedIds.has(menuId)) return false;

    const children = childrenByParent.get(menuId) ?? [];
    return children.every(childId => isWholeBranchSelected(childId));
  }

  // 半选父节点也保存在 menuIds 中，但回显时不能直接勾选它，
  // 否则树组件会级联选中原本没有授权的其他子节点。
  return menuIds.filter(menuId => {
    const children = childrenByParent.get(menuId) ?? [];
    return children.length === 0 || isWholeBranchSelected(menuId);
  });
}

function selectAllMenus() {
  menuTreeRef.value?.setCheckedKeys(menus.value.map(menu => menu.id));
  syncMenuIds();
}

function clearAllMenus() {
  menuTreeRef.value?.setCheckedKeys([]);
  syncMenuIds();
}

function menuTypeLabel(type: Api.SystemManage.FastApiMenuType) {
  const labels: Record<Api.SystemManage.FastApiMenuType, string> = {
    directory: '目录',
    page: '页面',
    button: '按钮'
  };

  return labels[type];
}

async function handleSubmit() {
  await validate();
  syncMenuIds();
  submitting.value = true;

  const form = model.value;
  const { error } =
    props.operateType === 'add'
      ? await fetchCreateFastApiRole(form)
      : await fetchUpdateFastApiRole(props.rowData!.id, {
          name: form.name,
          description: form.description,
          enabled: form.enabled,
          menuIds: form.menuIds
        });
  submitting.value = false;
  if (error) return;

  window.$message?.success($t(props.operateType === 'add' ? 'common.addSuccess' : 'common.updateSuccess'));
  closeDrawer();
  emit('submitted');
}

watch(visible, async isVisible => {
  if (!isVisible) return;

  handleInitModel();
  restoreValidation();
  await loadMenus();
  await nextTick();
  menuTreeRef.value?.setCheckedKeys(getMenuRestoreKeys(model.value.menuIds));
});
</script>

<template>
  <ElDrawer v-model="visible" :size="480" class="manage-operate-drawer">
    <template #header>
      <div class="operate-drawer-heading">
        <span class="operate-drawer-icon"><icon-material-symbols-shield-outline-rounded /></span>
        <div>
          <strong>{{ title }}</strong>
          <small>{{ $t('page.manage.common.permissionInfo') }}</small>
        </div>
      </div>
    </template>
    <ElForm ref="formRef" :model="model" :rules="rules" label-position="top" class="operate-form">
      <ElFormItem :label="$t('page.manage.role.roleName')" prop="name">
        <ElInput v-model="model.name" :placeholder="$t('page.manage.role.form.roleName')" />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.role.roleCode')" prop="code">
        <ElInput
          v-model="model.code"
          :placeholder="$t('page.manage.role.form.roleCode')"
          :disabled="props.operateType === 'edit'"
        />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.role.roleStatus')" prop="enabled">
        <ElSwitch v-model="model.enabled" />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.role.roleDesc')" prop="description">
        <ElInput
          v-model="model.description"
          type="textarea"
          :rows="3"
          :placeholder="$t('page.manage.role.form.roleDesc')"
        />
      </ElFormItem>
      <ElFormItem :label="$t('page.manage.role.menuAuth')" prop="menuIds">
        <div class="role-menu-auth">
          <div class="role-menu-auth__toolbar">
            <span>已选择 {{ selectedMenuCount }} 项</span>
            <ElSpace :size="8">
              <ElButton text type="primary" @click="selectAllMenus">全选</ElButton>
              <ElButton text @click="clearAllMenus">清空</ElButton>
            </ElSpace>
          </div>
          <ElTree
            ref="menuTreeRef"
            v-loading="menuLoading"
            :data="menuTree"
            node-key="id"
            show-checkbox
            default-expand-all
            :empty-text="menuLoading ? '正在加载菜单...' : '暂无菜单数据'"
            @check="syncMenuIds"
          >
            <template #default="{ data }">
              <span class="role-menu-auth__node">
                <span>{{ data.title }}</span>
                <span class="role-menu-auth__type">{{ menuTypeLabel(data.menuType) }}</span>
                <code v-if="data.permissionCode">{{ data.permissionCode }}</code>
              </span>
            </template>
          </ElTree>
        </div>
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
.role-menu-auth {
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
}
.role-menu-auth__toolbar {
  display: flex;
  min-height: 42px;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.role-menu-auth .el-tree {
  min-height: 160px;
  max-height: 360px;
  overflow-y: auto;
  padding: 8px;
}
.role-menu-auth__node {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}
.role-menu-auth__type {
  flex: none;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  font-size: 11px;
}
.role-menu-auth__node code {
  overflow: hidden;
  color: var(--el-text-color-placeholder);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
