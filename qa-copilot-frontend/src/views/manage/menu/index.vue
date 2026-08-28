<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Ref } from 'vue';
import { useBoolean } from '@sa/hooks';
import { fetchDeleteFastApiMenu, fetchGetFastApiMenuList } from '@/service/api';
import { $t } from '@/locales';
import MenuOperateModal, { type OperateType } from './modules/menu-operate-modal.vue';

type MenuRow = Api.SystemManage.FastApiMenu & { children?: MenuRow[] };

const { bool: visible, setTrue: openModal } = useBoolean();
const loading = ref(false);
const searchKeyword = ref('');
const menuRecords = ref<Api.SystemManage.FastApiMenu[]>([]);
const selectedId = ref<number | null>(null);

const menuTypeLabels: Record<Api.SystemManage.FastApiMenuType, App.I18n.I18nKey> = {
  directory: 'page.manage.menu.type.directory',
  page: 'page.manage.menu.type.menu',
  button: 'page.manage.menu.button'
};

function getMenuTypeLabel(item: Api.SystemManage.FastApiMenu) {
  return $t(menuTypeLabels[item.menuType]);
}

function buildMenuTree(records: Api.SystemManage.FastApiMenu[]): MenuRow[] {
  const map = new Map<number, MenuRow>(records.map(item => [item.id, { ...item }]));
  const roots: MenuRow[] = [];

  map.forEach(item => {
    const parent = item.parentId === null ? undefined : map.get(item.parentId);
    if (!parent) {
      roots.push(item);
      return;
    }

    parent.children ??= [];
    parent.children.push(item);
  });

  return roots;
}

function filterMenuTree(rows: MenuRow[], keyword: string): MenuRow[] {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return rows;

  return rows.flatMap(row => {
    const children = filterMenuTree(row.children || [], normalizedKeyword);
    const values = [row.title, row.routeName, row.path, row.component, row.permissionCode || ''];
    const matched = values.some(value => value.toLowerCase().includes(normalizedKeyword));

    return matched || children.length ? [{ ...row, children: children.length ? children : undefined }] : [];
  });
}

const menuTree = computed(() => buildMenuTree(menuRecords.value));
const filteredTree = computed(() => filterMenuTree(menuTree.value, searchKeyword.value));
const selectedMenu = computed(() => menuRecords.value.find(item => item.id === selectedId.value) || null);
const selectedParent = computed(() => {
  if (!selectedMenu.value?.parentId) return null;
  return menuRecords.value.find(item => item.id === selectedMenu.value?.parentId) || null;
});

const menuCounts = computed(() => {
  return menuRecords.value.reduce(
    (counts, item) => {
      counts[item.menuType] += 1;
      return counts;
    },
    { directory: 0, page: 0, button: 0 }
  );
});

async function getData() {
  loading.value = true;
  try {
    const { data, error } = await fetchGetFastApiMenuList();
    if (error) return;

    menuRecords.value = data;
    if (!data.some(item => item.id === selectedId.value)) {
      selectedId.value = data[0]?.id ?? null;
    }
  } finally {
    loading.value = false;
  }
}

const operateType = ref<OperateType>('add');
const editingData: Ref<Api.SystemManage.FastApiMenu | null> = ref(null);

function handleAdd() {
  operateType.value = 'add';
  editingData.value = null;
  openModal();
}

function handleSelect(item: MenuRow) {
  selectedId.value = item.id;
}

function handleEdit(item: Api.SystemManage.FastApiMenu) {
  operateType.value = 'edit';
  editingData.value = { ...item };
  openModal();
}

function handleAddChildMenu(item: Api.SystemManage.FastApiMenu) {
  operateType.value = 'addChild';
  editingData.value = { ...item };
  openModal();
}

async function handleDelete(id: number) {
  const { error } = await fetchDeleteFastApiMenu(id);
  if (error) return;

  window.$message?.success($t('common.deleteSuccess'));
  selectedId.value = null;
  await getData();
}

getData();
</script>

<template>
  <div class="menu-page">
    <div class="menu-workbench">
      <aside class="menu-browser">
        <header class="menu-browser__header">
          <div class="menu-browser__title-row">
            <div>
              <h2>{{ $t('page.manage.menu.title') }}</h2>
              <p>
                {{ menuCounts.directory }} {{ $t('page.manage.menu.type.directory') }} · {{ menuCounts.page }}
                {{ $t('page.manage.menu.type.menu') }} · {{ menuCounts.button }} {{ $t('page.manage.menu.button') }}
              </p>
            </div>
            <ElTooltip :content="$t('common.add')" placement="bottom">
              <ElButton type="primary" class="header-add" @click="handleAdd">
                <icon-ic-round-plus />
              </ElButton>
            </ElTooltip>
          </div>
          <ElInput v-model="searchKeyword" clearable :placeholder="$t('page.manage.menu.searchPlaceholder')">
            <template #prefix><icon-ic-round-search class="text-icon" /></template>
          </ElInput>
        </header>

        <div v-loading="loading" class="menu-tree-wrap">
          <ElTree
            :key="searchKeyword.trim() ? `search-${searchKeyword}` : 'menu-tree'"
            :data="filteredTree"
            :default-expand-all="Boolean(searchKeyword.trim())"
            :expand-on-click-node="false"
            :highlight-current="true"
            :current-node-key="selectedId ?? undefined"
            node-key="id"
            class="menu-tree"
            @node-click="handleSelect"
          >
            <template #default="{ data: item }">
              <div class="menu-tree-item">
                <span class="menu-tree-item__icon">
                  <icon-material-symbols-folder-outline-rounded v-if="item.menuType === 'directory'" />
                  <icon-material-symbols-description-outline-rounded v-else-if="item.menuType === 'page'" />
                  <icon-material-symbols-touch-app-outline-rounded v-else />
                </span>
                <div class="menu-tree-item__content">
                  <span class="menu-tree-item__title">{{ item.title }}</span>
                  <span class="menu-tree-item__route">{{ item.routeName }}</span>
                </div>
                <span class="menu-tree-item__type">{{ getMenuTypeLabel(item) }}</span>
              </div>
            </template>
          </ElTree>
        </div>
      </aside>

      <main class="menu-detail">
        <template v-if="selectedMenu">
          <header class="menu-detail__header">
            <div class="menu-detail__identity">
              <span class="menu-detail__icon">
                <icon-material-symbols-folder-outline-rounded v-if="selectedMenu.menuType === 'directory'" />
                <icon-material-symbols-description-outline-rounded v-else-if="selectedMenu.menuType === 'page'" />
                <icon-material-symbols-touch-app-outline-rounded v-else />
              </span>
              <div>
                <h1>{{ selectedMenu.title }}</h1>
                <p>{{ selectedMenu.routeName }}</p>
              </div>
            </div>
            <div class="menu-detail__actions">
              <ElButton v-if="selectedMenu.menuType !== 'button'" @click="handleAddChildMenu(selectedMenu)">
                <template #icon><icon-ic-round-plus /></template>
                {{ $t('page.manage.menu.addChildMenu') }}
              </ElButton>
              <ElButton type="primary" @click="handleEdit(selectedMenu)">
                <template #icon><icon-material-symbols-edit-outline-rounded /></template>
                {{ $t('common.edit') }}
              </ElButton>
              <ElPopconfirm :title="$t('common.confirmDelete')" @confirm="handleDelete(selectedMenu.id)">
                <template #reference>
                  <ElButton class="detail-delete" :aria-label="$t('common.delete')">
                    <icon-ic-round-delete />
                  </ElButton>
                </template>
              </ElPopconfirm>
            </div>
          </header>

          <div class="menu-detail__content">
            <section class="detail-section">
              <div class="detail-section__heading">
                <icon-material-symbols-tune-rounded />
                <h3>{{ $t('page.manage.menu.basicInfo') }}</h3>
              </div>
              <dl class="detail-list">
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.menuType') }}</dt>
                  <dd>
                    <span class="detail-type">{{ getMenuTypeLabel(selectedMenu) }}</span>
                  </dd>
                </div>
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.parentId') }}</dt>
                  <dd>{{ selectedParent?.title || $t('page.manage.menu.rootMenu') }}</dd>
                </div>
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.id') }}</dt>
                  <dd class="is-mono">{{ selectedMenu.id }}</dd>
                </div>
              </dl>
            </section>

            <section class="detail-section">
              <div class="detail-section__heading">
                <icon-material-symbols-alt-route-rounded />
                <h3>{{ $t('page.manage.menu.routeConfig') }}</h3>
              </div>
              <dl class="detail-list">
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.routeName') }}</dt>
                  <dd class="is-mono">{{ selectedMenu.routeName }}</dd>
                </div>
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.routePath') }}</dt>
                  <dd class="is-mono">{{ selectedMenu.path || '-' }}</dd>
                </div>
                <div class="detail-row">
                  <dt>
                    {{
                      selectedMenu.menuType === 'button'
                        ? $t('page.manage.menu.buttonCode')
                        : $t('page.manage.menu.page')
                    }}
                  </dt>
                  <dd class="is-mono">
                    {{ selectedMenu.menuType === 'button' ? selectedMenu.permissionCode : selectedMenu.component }}
                  </dd>
                </div>
              </dl>
            </section>

            <section class="detail-section">
              <div class="detail-section__heading">
                <icon-material-symbols-visibility-outline-rounded />
                <h3>{{ $t('page.manage.menu.displaySettings') }}</h3>
              </div>
              <dl class="detail-list">
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.menuStatus') }}</dt>
                  <dd>
                    <span class="detail-status" :class="[selectedMenu.enabled ? 'is-enabled' : 'is-disabled']">
                      <span />
                      {{
                        $t(
                          selectedMenu.enabled
                            ? 'page.manage.common.status.enable'
                            : 'page.manage.common.status.disable'
                        )
                      }}
                    </span>
                  </dd>
                </div>
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.hideInMenu') }}</dt>
                  <dd>{{ $t(selectedMenu.hidden ? 'common.yesOrNo.yes' : 'common.yesOrNo.no') }}</dd>
                </div>
                <div class="detail-row">
                  <dt>{{ $t('page.manage.menu.order') }}</dt>
                  <dd class="is-mono">{{ selectedMenu.order }}</dd>
                </div>
              </dl>
            </section>
          </div>
        </template>

        <ElEmpty v-else :description="$t('common.noData')" />
      </main>
    </div>

    <MenuOperateModal
      v-model:visible="visible"
      :operate-type="operateType"
      :row-data="editingData"
      :menu-options="menuRecords"
      @submitted="getData"
    />
  </div>
</template>

<style lang="scss" scoped>
.menu-page {
  height: 100%;
  min-height: 500px;
  overflow: hidden;
}

.menu-workbench {
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  box-shadow:
    0 1px 2px rgb(0 0 0 / 3%),
    0 8px 24px rgb(0 0 0 / 2%);
}

.menu-browser {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color-lighter);
}

.menu-browser__header {
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.menu-browser__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.menu-browser h2,
.menu-detail h1,
.detail-section h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  letter-spacing: 0;
}

.menu-browser h2 {
  font-size: 16px;
  font-weight: 650;
  line-height: 1.4;
}

.menu-browser__title-row p {
  margin: 3px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.header-add {
  width: 32px;
  height: 32px;
  padding: 0;
  font-size: 18px;
}

.menu-tree-wrap {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 8px;
}

.menu-tree {
  --el-tree-node-hover-bg-color: var(--el-fill-color-light);
  background: transparent;
}

.menu-tree-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-width: 0;
  padding-right: 8px;
}

.menu-tree-item__icon {
  flex: 0 0 17px;
  color: var(--el-text-color-secondary);
  font-size: 17px;
}

.menu-tree-item__content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.menu-tree-item__title,
.menu-tree-item__route {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-tree-item__title {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.35;
}

.menu-tree-item__route {
  margin-top: 2px;
  color: var(--el-text-color-placeholder);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.25;
}

.menu-tree-item__type,
.detail-type {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-extra-light);
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 20px;
}

.menu-tree-item__type {
  flex: none;
  padding: 0 6px;
}

.menu-detail {
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.menu-detail__header {
  position: sticky;
  z-index: 2;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 72px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  padding: 12px 20px;
}

.menu-detail__identity {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.menu-detail__icon {
  display: inline-flex;
  flex: 0 0 36px;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 7px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 19px;
}

.menu-detail h1 {
  overflow: hidden;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-detail__identity p {
  margin: 3px 0 0;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.menu-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-delete {
  width: 32px;
  padding: 0;
  color: var(--el-text-color-secondary);
}

.detail-delete:hover {
  border-color: rgb(var(--error-color) / 35%);
  background: rgb(var(--error-color) / 7%);
  color: rgb(var(--error-color));
}

.menu-detail__content {
  width: min(760px, calc(100% - 48px));
  margin: 0 auto;
  padding: 28px 0 48px;
}

.detail-section + .detail-section {
  margin-top: 30px;
}

.detail-section__heading {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 12px;
}

.detail-section__heading > :first-child {
  color: var(--el-text-color-secondary);
  font-size: 17px;
}

.detail-section h3 {
  font-size: 14px;
  font-weight: 650;
}

.detail-list {
  margin: 0;
  border-top: 1px solid var(--el-border-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-row {
  display: grid;
  grid-template-columns: minmax(120px, 32%) minmax(0, 1fr);
  align-items: center;
  min-height: 48px;
  gap: 24px;
  padding: 8px 14px;
}

.detail-row + .detail-row {
  border-top: 1px solid var(--el-border-color-extra-light);
}

.detail-row dt,
.detail-row dd {
  margin: 0;
}

.detail-row dt {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.detail-row dd {
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-row dd.is-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.detail-type {
  display: inline-block;
  padding: 0 7px;
}

.detail-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--el-text-color-secondary);
}

.detail-status > span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
}

.detail-status.is-enabled > span {
  background: rgb(var(--success-color));
}

:deep(.menu-tree .el-tree-node__content) {
  height: 46px;
  margin-bottom: 2px;
  border-radius: 6px;
}

:deep(.menu-tree .el-tree-node__expand-icon) {
  color: var(--el-text-color-placeholder);
}

:deep(.menu-tree .el-tree-node.is-current > .el-tree-node__content) {
  background: var(--el-fill-color-light);
}

.header-add:active,
.menu-detail__actions :deep(.el-button:active) {
  transform: scale(0.97);
}

@media (max-width: 760px) {
  .menu-page {
    height: auto;
    overflow: visible;
  }

  .menu-workbench {
    display: block;
    height: auto;
    overflow: visible;
  }

  .menu-browser {
    height: 380px;
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .menu-detail__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .menu-detail__actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .menu-detail__content {
    width: auto;
    padding: 22px 16px 36px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .header-add,
  .menu-detail__actions :deep(.el-button) {
    transition-duration: 0.01ms !important;
  }
}
</style>
