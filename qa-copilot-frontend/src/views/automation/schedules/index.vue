<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import dayjs from 'dayjs';
import {
  fetchCreateAutomationSchedule,
  fetchDeleteAutomationSchedule,
  fetchGetAutomationDefinitionList,
  fetchGetAutomationSchedules,
  fetchGetProjectList,
  fetchGetTestEnvironments,
  fetchUpdateAutomationSchedule
} from '@/service/api';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'AutomationSchedules' });
const authStore = useAuthStore();
const projects = ref<Api.ProjectManage.Project[]>([]);
const projectId = ref<number | null>(null);
const definitions = ref<Api.AutomationManage.Definition[]>([]);
const environments = ref<Api.ProjectManage.TestEnvironment[]>([]);
const records = ref<Api.AutomationManage.Schedule[]>([]);
const loading = ref(false);
const saving = ref(false);
const visible = ref(false);
const editing = ref<Api.AutomationManage.Schedule | null>(null);
const form = reactive<Api.AutomationManage.ScheduleParams>({
  name: '',
  definitionId: 0,
  environmentId: 0,
  cronExpression: '0 2 * * *',
  timezone: 'Asia/Shanghai',
  timeoutSeconds: 300,
  enabled: true
});
const canManage = computed(
  () => authStore.userInfo.buttons.includes('*') || authStore.userInfo.buttons.includes('automation:definition:manage')
);
const cronPresets = [
  { label: '每天凌晨 2 点', value: '0 2 * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '工作日早上 9 点', value: '0 9 * * 1-5' },
  { label: '每周一凌晨 2 点', value: '0 2 * * 1' }
];

async function loadProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (!error) {
    projects.value = data.records;
    projectId.value = projects.value[0]?.id ?? null;
  }
}
async function loadData() {
  if (!projectId.value) return;
  loading.value = true;
  const [scheduleResult, definitionResult, environmentResult] = await Promise.all([
    fetchGetAutomationSchedules(projectId.value),
    fetchGetAutomationDefinitionList(projectId.value, { current: 1, size: 100, keyword: '', status: 'APPROVED' }),
    fetchGetTestEnvironments(projectId.value, { keyword: '', enabled: true })
  ]);
  loading.value = false;
  if (!scheduleResult.error) records.value = scheduleResult.data;
  if (!definitionResult.error) definitions.value = definitionResult.data.records;
  if (!environmentResult.error)
    environments.value = environmentResult.data.filter(item => item.enabled && item.environmentType !== 'PRODUCTION');
}
function open(row?: Api.AutomationManage.Schedule) {
  editing.value = row ?? null;
  Object.assign(
    form,
    row
      ? {
          name: row.name,
          definitionId: row.definitionId,
          environmentId: row.environmentId,
          cronExpression: row.cronExpression,
          timezone: row.timezone,
          timeoutSeconds: row.timeoutSeconds,
          enabled: row.enabled
        }
      : {
          name: '',
          definitionId: definitions.value[0]?.id ?? 0,
          environmentId: environments.value[0]?.id ?? 0,
          cronExpression: '0 2 * * *',
          timezone: 'Asia/Shanghai',
          timeoutSeconds: 300,
          enabled: true
        }
  );
  visible.value = true;
}
async function save() {
  if (!projectId.value || !form.name.trim() || !form.definitionId || !form.environmentId)
    return window.$message?.warning('请补全必填项');
  saving.value = true;
  const result = editing.value
    ? await fetchUpdateAutomationSchedule(projectId.value, editing.value.id, form)
    : await fetchCreateAutomationSchedule(projectId.value, form);
  saving.value = false;
  if (!result.error) {
    visible.value = false;
    window.$message?.success('定时回归计划已保存');
    await loadData();
  }
}
async function remove(row: Api.AutomationManage.Schedule) {
  if (!projectId.value) return;
  const { error } = await fetchDeleteAutomationSchedule(projectId.value, row.id);
  if (!error) {
    window.$message?.success('计划已删除');
    await loadData();
  }
}
watch(projectId, loadData);
onMounted(loadProjects);
</script>

<template>
  <div class="h-full min-h-0">
    <ElCard class="h-full">
      <template #header>
        <div class="schedule-heading">
          <div>
            <h2>定时回归</h2>
            <p>到期后自动提交已审批接口定义，仍经过事务性发件箱和受控执行器</p>
          </div>
          <div class="schedule-actions">
            <ElSelect v-model="projectId" filterable placeholder="选择项目" style="width: 240px">
              <ElOption v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
            </ElSelect>
            <ElButton v-if="canManage" type="primary" @click="open()">
              <SvgIcon icon="mdi:plus" />
              新增计划
            </ElButton>
          </div>
        </div>
      </template>
      <ElAlert type="info" :closable="false" title="不会直接在调度器中执行">
        计划到期只创建普通自动化任务；生产环境、停用环境和非审批定义仍会被拒绝。
      </ElAlert>
      <ElTable v-loading="loading" border :data="records" class="mt-4">
        <ElTableColumn label="计划" min-width="220">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <div class="schedule-sub">{{ row.definitionName }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="environmentName" label="环境" min-width="160" />
        <ElTableColumn label="周期" min-width="190">
          <template #default="{ row }">
            <code>{{ row.cronExpression }}</code>
            <div class="schedule-sub">{{ row.timezone }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="下次执行" width="170">
          <template #default="{ row }">{{ dayjs(row.nextRunAt).format('YYYY-MM-DD HH:mm') }}</template>
        </ElTableColumn>
        <ElTableColumn label="最近执行" width="170">
          <template #default="{ row }">
            {{ row.lastRunAt ? dayjs(row.lastRunAt).format('YYYY-MM-DD HH:mm') : '尚未执行' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90">
          <template #default="{ row }">
            <ElTag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn v-if="canManage" label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <ElButton text circle @click="open(row)"><SvgIcon icon="mdi:pencil-outline" /></ElButton>
            <ElPopconfirm :title="`删除计划“${row.name}”？`" @confirm="remove(row)">
              <template #reference>
                <ElButton text circle type="danger"><SvgIcon icon="mdi:delete-outline" /></ElButton>
              </template>
            </ElPopconfirm>
          </template>
        </ElTableColumn>
        <template #empty><ElEmpty description="暂无定时回归计划" /></template>
      </ElTable>
    </ElCard>
    <ElDrawer v-model="visible" :size="560" :title="editing ? '编辑定时回归' : '新增定时回归'">
      <ElForm label-position="top">
        <ElFormItem label="计划名称" required><ElInput v-model="form.name" /></ElFormItem>
        <ElFormItem label="已审批自动化定义" required>
          <ElSelect v-model="form.definitionId" class="w-full">
            <ElOption
              v-for="item in definitions"
              :key="item.id"
              :label="`${item.name} · V${item.version}`"
              :value="item.id"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="测试环境" required>
          <ElSelect v-model="form.environmentId" class="w-full">
            <ElOption v-for="item in environments" :key="item.id" :label="item.name" :value="item.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="常用周期">
          <ElSelect v-model="form.cronExpression" allow-create filterable class="w-full">
            <ElOption
              v-for="item in cronPresets"
              :key="item.value"
              :label="`${item.label}（${item.value}）`"
              :value="item.value"
            />
          </ElSelect>
        </ElFormItem>
        <div class="schedule-grid">
          <ElFormItem label="时区"><ElInput v-model="form.timezone" /></ElFormItem>
          <ElFormItem label="任务超时（秒）">
            <ElInputNumber v-model="form.timeoutSeconds" :min="10" :max="7200" class="w-full" />
          </ElFormItem>
        </div>
        <ElFormItem label="启用"><ElSwitch v-model="form.enabled" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="visible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="save">保存</ElButton>
      </template>
    </ElDrawer>
  </div>
</template>

<style scoped lang="scss">
.schedule-heading,
.schedule-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.schedule-heading h2 {
  margin: 0;
  font-size: 18px;
}
.schedule-heading p,
.schedule-sub {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.schedule-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 700px) {
  .schedule-heading,
  .schedule-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .schedule-grid {
    grid-template-columns: 1fr;
  }
}
</style>
