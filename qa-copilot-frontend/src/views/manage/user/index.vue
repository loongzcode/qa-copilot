<script setup lang="tsx">
import { computed, ref } from 'vue';
import dayjs from 'dayjs';
import { fetchDeleteFastApiUser, fetchGetFastApiUserList } from '@/service/api';
import { defaultTransform, useTableOperate, useUIPaginatedTable } from '@/hooks/common/table';
import { $t } from '@/locales';
import UserOperateDrawer from './modules/user-operate-drawer.vue';

defineOptions({ name: 'UserManage' });

const searchParams = ref<Api.SystemManage.FastApiUserSearchParams>({
  current: 1,
  size: 30,
  keyword: undefined
});

function getInitial(row: Api.SystemManage.FastApiUser) {
  return (row.displayName || row.username).trim().slice(0, 1) || '?';
}

const { columns, columnChecks, data, getData, getDataByPage, loading, mobilePagination } = useUIPaginatedTable<
  Awaited<ReturnType<typeof fetchGetFastApiUserList>>,
  Api.SystemManage.FastApiUser
>({
  paginationProps: {
    currentPage: searchParams.value.current,
    pageSize: searchParams.value.size
  },
  api: () => fetchGetFastApiUserList(searchParams.value),
  transform: response => defaultTransform(response),
  onPaginationParamsChange: params => {
    searchParams.value.current = params.currentPage;
    searchParams.value.size = params.pageSize;
  },
  columns: () => [
    { prop: 'index', type: 'index', label: $t('common.index'), width: 58, align: 'center' },
    {
      prop: 'username',
      label: $t('page.manage.user.userName'),
      minWidth: 220,
      formatter: row => (
        <div class="user-identity-cell">
          <span class="user-table-avatar">{getInitial(row)}</span>
          <span class="user-identity-copy">
            <strong>{row.displayName || row.username}</strong>
            <small>@{row.username}</small>
          </span>
        </div>
      )
    },
    {
      prop: 'roleCodes',
      label: $t('page.manage.user.userRole'),
      minWidth: 220,
      formatter: row => (
        <div class="table-chip-list">
          {row.roleCodes.length ? (
            row.roleCodes.map(code => <span class="table-chip">{code}</span>)
          ) : (
            <span class="table-empty">-</span>
          )}
        </div>
      )
    },
    {
      prop: 'isActive',
      label: $t('page.manage.user.userStatus'),
      align: 'center',
      width: 100,
      formatter: row => (
        <span class={['table-status', row.isActive ? 'is-enabled' : 'is-disabled']}>
          <span />
          {$t(row.isActive ? 'page.manage.common.status.enable' : 'page.manage.common.status.disable')}
        </span>
      )
    },
    {
      prop: 'createdAt',
      label: $t('page.manage.common.createdAt'),
      minWidth: 160,
      formatter: row => <span class="table-date">{dayjs(row.createdAt).format('YYYY-MM-DD HH:mm')}</span>
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
                  content={row.isSuperuser ? $t('page.manage.user.superuserDeleteDisabled') : $t('common.delete')}
                  placement="top"
                >
                  <ElButton text circle class="table-row-action is-danger" disabled={row.isSuperuser}>
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

async function handleDelete(userId: number) {
  const { error } = await fetchDeleteFastApiUser(userId);
  if (error) return;

  window.$message?.success($t('common.deleteSuccess'));
  await getData();
}
</script>

<template>
  <div class="manage-table-page user-manage-page">
    <ElCard class="manage-table-card">
      <template #header>
        <div class="manage-table-header">
          <div>
            <h2>{{ $t('page.manage.user.title') }}</h2>
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
          v-model="searchParams.keyword"
          clearable
          class="manage-table-search"
          :placeholder="$t('page.manage.user.searchPlaceholder')"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix><icon-ic-round-search /></template>
        </ElInput>
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

      <UserOperateDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getDataByPage"
      />
    </ElCard>
  </div>
</template>

<style src="../components/manage-table.scss" lang="scss"></style>
