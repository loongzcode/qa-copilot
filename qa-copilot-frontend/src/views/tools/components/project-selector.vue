<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchGetProjectList } from '@/service/api';

const projectId = defineModel<number | null>({ required: true });
const projects = ref<Api.ProjectManage.Project[]>([]);

async function loadProjects() {
  const { data, error } = await fetchGetProjectList({ current: 1, size: 200, keyword: '' });
  if (error) return;
  projects.value = data.records;
  if (!projectId.value || !projects.value.some(item => item.id === projectId.value)) {
    projectId.value = projects.value[0]?.id ?? null;
  }
}

onMounted(loadProjects);
</script>

<template>
  <ElSelect v-model="projectId" filterable placeholder="选择项目" class="tool-project-select">
    <ElOption v-for="item in projects" :key="item.id" :label="`${item.name}（${item.code}）`" :value="item.id" />
  </ElSelect>
</template>

<style scoped>
.tool-project-select {
  width: 260px;
  max-width: 100%;
}
</style>
