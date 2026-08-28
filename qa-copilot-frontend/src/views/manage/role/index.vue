<script setup lang="tsx">
import { computed, ref } from 'vue';
import dayjs from 'dayjs';
import { fetchDeleteFastApiRole, fetchGetFastApiRoleList } from '@/service/api';
import { useTableOperate, useUIPaginatedTable } from '@/hooks/common/table';
import { $t } from '@/locales';
import RoleOperateDrawer from './modules/role-operate-drawer.vue';

defineOptions({ name: 'RoleManage' });

const current = ref(1);
const pageSize = ref(10);
const keyword = ref('');
const status = ref<'all' | 'enabled' | 'disabled'>('all');

const { columns, columnChecks, data, loading, getData, getDataByPage, mobilePagination } = useUIPaginatedTable<
  Awaited<ReturnType<typeof fetchGetFastApiRoleList>>,
  Api.SystemManage.FastApiRole
>({
  paginationProps: {
    currentPage: current.value,
    pageSize: pageSize.value
  },
  api: () => fetchGetFastApiRoleList(),
  transform: response => {
    if (response.error) return { data: [], pageNum: 1, pageSize: 10, total: 0 };

    const normalizedKeyword = keyword.value.trim().toLowerCase();
    const records = response.data.filter(item => {
      const matchesKeyword =
        !normalizedKeyword || `${item.name} ${item.code}`.toLowerCase().includes(normalizedKeyword);
      const matchesStatus = status.value === 'all' || item.enabled === (status.value === 'enabled');
      return matchesKeyword && matchesStatus;
    });
    const start = (current.value - 1) * pageSize.value;

    return {
      data: records.slice(start, start + pageSize.value),
      pageNum: current.value,
      pageSize: pageSize.value,
      total: records.length
    };
  },
  onPaginationParamsChange: params => {
    current.value = params.currentPage ?? 1;
    pageSize.value = params.pageSize ?? 10;
  },
  columns: () => [
    { prop: 'index', type: 'index', label: $t('common.index'), width: 58, align: 'center' },
    {
      prop: 'name',
      label: $t('page.manage.role.roleName'),
      minWidth: 220,
      formatter: row => (
        <div class="role-identity-cell">
          <span class="role-table-icon">
            <icon-material-symbols-shield-outline-rounded />
          </span>
          <span class="role-identity-copy">
            <strong>{row.name}</strong>
            <small>{row.code}</small>
          </span>
        </div>
      )
    },
    {
      prop: 'description',
      label: $t('page.manage.role.roleDesc'),
      minWidth: 260,
      showOverflowTooltip: true,
      formatter: row => row.description || <span class="table-empty">-</span>
    },
    {
      prop: 'menuIds',
      label: $t('page.manage.role.menuAuth'),
      align: 'center',
      width: 110,
      formatter: row => <span class="role-menu-count">{row.menuIds.length}</span>
    },
    {
      prop: 'isSystem',
      label: $t('page.manage.role.systemRole'),
      align: 'center',
      width: 100,
      formatter: row =>
        row.isSystem ? (
          <span class="table-chip">{$t('page.manage.role.systemBuiltIn')}</span>
        ) : (
          <span class="table-empty">-</span>
        )
    },
    {
      prop: 'enabled',
      label: $t('page.manage.role.roleStatus'),
      align: 'center',
      width: 100,
      formatter: row => (
        <span class={['table-status', row.enabled ? 'is-enabled' : 'is-disabled']}>
          <span />
          {$t(row.enabled ? 'page.manage.common.status.enable' : 'page.manage.common.status.disable')}
        </span>
      )
    },
    {
      prop: 'updatedAt',
      label: $t('page.manage.common.updatedAt'),
      minWidth: 160,
      formatter: row => <span class="table-date">{dayjs(row.updatedAt).format('YYYY-MM-DD HH:mm')}</span>
    },
    {
      prop: 'operate',
      label: $t('common.operate'),
      align: 'right',
      width: 112,
      formatter: row => (
        <div class="table-row-actions">
          <ElTooltip content={$t('common.edit')} placement="top">
            <ElButton text circle class="table-row-action" onClick={() => handleEdit(row.id)}>
              <icon-material-symbols-edit-outline-rounded />
            </ElButton>
          </ElTooltip>
          <ElPopconfirm title={$t('common.confirmDelete')} onConfirm={() => handleDelete(row.id)}>
            {{
              reference: () => (
                <ElTooltip
                  content={row.isSystem ? $t('page.manage.role.systemDeleteDisabled') : $t('common.delete')}
                  placement="top"
                >
                  <ElButton text circle class="table-row-action is-danger" disabled={row.isSystem}>
                    <icon-ic-round-delete />
                  </ElButton>
                </ElTooltip>
              )
            }}
          </ElPopconfirm>
        </div>
      )
    }
  ]
});

const total = computed(() => Number(mobilePagination.value.total || 0));
const { drawerVisible, operateType, editingData, handleAdd, handleEdit } = useTableOperate(data, 'id', getData);

function handleSearch() {
  getDataByPage(1);
}

async function handleDelete(id: number) {
  const { error } = await fetchDeleteFastApiRole(id);
  if (error) return;

  window.$message?.success($t('common.deleteSuccess'));
  await getData();
}
</script>

<template>
  <div class="manage-table-page role-manage-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>{{ $t('page.manage.role.title') }}</h2>
            <p>{{ $t('page.manage.common.total') }} {{ total }}</p>
          </div>
          <div class="manage-table-header__actions">
            <ElTooltip :content="$t('common.refresh')" placement="top">
              <ElButton class="header-icon-button" @click="getData">
                <icon-mdi-refresh :class="{ 'animate-spin': loading }" />
              </ElButton>
            </ElTooltip>
            <TableColumnSetting v-model:columns="columnChecks" />
            <ElButton type="primary" @click="handleAdd">
              <template #icon><icon-ic-round-plus /></template>
              {{ $t('common.add') }}
            </ElButton>
          </div>
        </div>
      </template>

      <div class="manage-table-toolbar">
        <ElInput
          v-model="keyword"
          clearable
          class="manage-table-search"
          :placeholder="$t('page.manage.role.searchPlaceholder')"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
        <ElSelect v-model="status" class="role-status-filter" @change="handleSearch">
          <ElOption :label="$t('page.manage.common.allStatus')" value="all" />
          <ElOption :label="$t('page.manage.common.status.enable')" value="enabled" />
          <ElOption :label="$t('page.manage.common.status.disable')" value="disabled" />
        </ElSelect>
      </div>

      <div class="manage-table-body">
        <ElTable v-loading="loading" height="100%" border class="mx-data-table" :data="data" row-key="id">
          <ElTableColumn v-for="col in columns" :key="col.prop" v-bind="col" />
        </ElTable>
      </div>

      <footer class="manage-table-footer">
        <ElPagination
          v-if="total"
          layout="total, prev, pager, next, sizes"
          v-bind="mobilePagination"
          @current-change="mobilePagination['current-change']"
          @size-change="mobilePagination['size-change']"
        />
      </footer>

      <RoleOperateDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getDataByPage"
      />
    </ElCard>
  </div>
</template>

<style src="../components/manage-table.scss" lang="scss"></style>

<style lang="scss">
.role-status-filter {
  width: 132px;
}

.role-menu-count {
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
}
</style>
