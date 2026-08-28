<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { renderAsync } from 'docx-preview';
import { fetchPreviewKnowledgeDocument } from '@/service/api';

defineOptions({ name: 'KnowledgeDocumentPreviewDialog' });

type PreviewKind = 'pdf' | 'docx' | 'text' | 'unsupported';

const visible = ref(false);
const loading = ref(false);
const citation = ref<Api.KnowledgeManage.KnowledgeCitation | null>(null);
const previewKind = ref<PreviewKind>('unsupported');
const previewUrl = ref('');
const previewFilename = ref('');
const textBefore = ref('');
const textMatch = ref('');
const textAfter = ref('');
const docxContainerRef = ref<HTMLElement>();

const dialogTitle = computed(() => citation.value?.documentTitle || '知识文档预览');
const pdfUrl = computed(() => {
  if (!previewUrl.value) return '';
  return citation.value?.pageNo ? `${previewUrl.value}#page=${citation.value.pageNo}` : previewUrl.value;
});

function clearObjectUrl() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = '';
}

function clearPreviewContent() {
  clearObjectUrl();
  previewKind.value = 'unsupported';
  previewFilename.value = '';
  textBefore.value = '';
  textMatch.value = '';
  textAfter.value = '';
  if (docxContainerRef.value) docxContainerRef.value.replaceChildren();
}

function buildTextPreview(fullText: string, evidence: string) {
  const needle = evidence.trim();
  const index = needle ? fullText.indexOf(needle) : -1;
  if (index < 0) {
    textBefore.value = fullText;
    return;
  }

  textBefore.value = fullText.slice(0, index);
  textMatch.value = fullText.slice(index, index + needle.length);
  textAfter.value = fullText.slice(index + needle.length);
}

function focusDocxEvidence(container: HTMLElement, currentCitation: Api.KnowledgeManage.KnowledgeCitation) {
  const needle = (currentCitation.sectionTitle || currentCitation.content.slice(0, 36)).trim();
  if (!needle) return;

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let textNode = walker.nextNode();
  while (textNode) {
    if (textNode.textContent?.includes(needle)) {
      const target = textNode.parentElement;
      target?.classList.add('knowledge-preview-hit');
      target?.scrollIntoView({ block: 'center' });
      return;
    }
    textNode = walker.nextNode();
  }
}

async function renderBlob(blob: Blob, currentCitation: Api.KnowledgeManage.KnowledgeCitation) {
  const mimeType = blob.type.toLowerCase();
  previewUrl.value = URL.createObjectURL(blob);

  if (mimeType === 'application/pdf') {
    previewKind.value = 'pdf';
    return;
  }

  if (mimeType.includes('wordprocessingml.document')) {
    previewKind.value = 'docx';
    await nextTick();
    if (!docxContainerRef.value) return;

    await renderAsync(blob, docxContainerRef.value, undefined, {
      breakPages: true,
      renderHeaders: true,
      renderFooters: true,
      renderFootnotes: true,
      renderEndnotes: true,
      ignoreLastRenderedPageBreak: false
    });
    focusDocxEvidence(docxContainerRef.value, currentCitation);
    return;
  }

  if (mimeType.startsWith('text/') || mimeType.includes('markdown')) {
    previewKind.value = 'text';
    buildTextPreview(await blob.text(), currentCitation.content);
    await nextTick();
    document.querySelector('.knowledge-text-preview mark')?.scrollIntoView({ block: 'center' });
    return;
  }

  previewKind.value = 'unsupported';
}

async function open(
  currentCitation: Api.KnowledgeManage.KnowledgeCitation,
  projectId: number,
  knowledgeBaseId: number
) {
  clearPreviewContent();
  citation.value = currentCitation;
  visible.value = true;
  loading.value = true;

  try {
    const result = await fetchPreviewKnowledgeDocument(projectId, knowledgeBaseId, currentCitation.documentId);
    previewFilename.value = result.filename || currentCitation.documentTitle;
    await renderBlob(result.blob, currentCitation);
  } catch (error) {
    visible.value = false;
    window.$message?.error(error instanceof Error ? error.message : '文档预览失败');
  } finally {
    loading.value = false;
  }
}

function downloadOriginal() {
  if (!previewUrl.value) return;
  const link = document.createElement('a');
  link.href = previewUrl.value;
  link.download = previewFilename.value || citation.value?.documentTitle || '知识文档';
  link.click();
}

function handleClosed() {
  citation.value = null;
  clearPreviewContent();
}

onBeforeUnmount(clearObjectUrl);

defineExpose({ open });
</script>

<template>
  <ElDialog
    v-model="visible"
    class="knowledge-preview-dialog"
    width="min(1180px, 96vw)"
    top="4vh"
    destroy-on-close
    append-to-body
    @closed="handleClosed"
  >
    <template #header>
      <div class="knowledge-preview-heading">
        <span><SvgIcon icon="mdi:file-eye-outline" /></span>
        <div>
          <strong>{{ dialogTitle }}</strong>
          <small v-if="citation">{{ citation.sectionTitle || `切片 ${citation.chunkIndex + 1}` }}</small>
        </div>
      </div>
    </template>

    <div v-loading="loading" class="knowledge-preview-body">
      <div v-if="citation" class="knowledge-preview-location">
        <SvgIcon icon="mdi:map-marker-text-outline" />
        <span>{{ citation.pageNo ? `第 ${citation.pageNo} 页` : '原文位置' }}</span>
        <span v-if="citation.sectionTitle">{{ citation.sectionTitle }}</span>
        <span v-if="citation.moduleName">模块：{{ citation.moduleName }}</span>
      </div>

      <iframe v-if="previewKind === 'pdf' && pdfUrl" :src="pdfUrl" title="PDF 原文预览" />

      <div v-show="previewKind === 'docx'" ref="docxContainerRef" class="knowledge-docx-preview" />

      <pre
        v-if="previewKind === 'text'"
        class="knowledge-text-preview"
      ><span>{{ textBefore }}</span><mark v-if="textMatch">{{ textMatch }}</mark><span>{{ textAfter }}</span></pre>

      <ElEmpty
        v-if="!loading && previewKind === 'unsupported'"
        description="当前文件格式无法在浏览器内预览，请下载原文件查看"
      />
    </div>

    <template #footer>
      <ElButton :disabled="!previewUrl" @click="downloadOriginal">
        <template #icon><SvgIcon icon="mdi:download-outline" /></template>
        下载原文件
      </ElButton>
      <ElButton type="primary" @click="visible = false">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<style lang="scss">
.knowledge-preview-dialog {
  .el-dialog__body {
    padding: 0 18px 18px;
  }
}

.knowledge-preview-heading {
  display: flex;
  align-items: center;
  gap: 10px;

  > span {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 9px;
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    font-size: 18px;
  }

  > div {
    display: flex;
    min-width: 0;
    flex-direction: column;
  }

  strong {
    overflow: hidden;
    max-width: min(760px, 70vw);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
  }
}

.knowledge-preview-body {
  position: relative;
  min-height: 68vh;
  max-height: 76vh;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.knowledge-preview-location {
  position: sticky;
  z-index: 3;
  top: 0;
  display: flex;
  align-items: center;
  min-height: 38px;
  padding: 8px 12px;
  gap: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: color-mix(in srgb, var(--el-bg-color) 94%, transparent);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  backdrop-filter: blur(8px);
}

.knowledge-preview-body iframe {
  display: block;
  width: 100%;
  height: calc(76vh - 40px);
  border: 0;
  background: white;
}

.knowledge-docx-preview {
  padding: 20px;

  .docx-wrapper {
    background: transparent;
  }

  .knowledge-preview-hit {
    border-radius: 3px;
    background: var(--el-color-warning-light-7) !important;
    box-shadow: 0 0 0 3px var(--el-color-warning-light-7);
  }
}

.knowledge-text-preview {
  min-height: calc(68vh - 40px);
  margin: 0;
  padding: 22px 26px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font-family: inherit;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;

  mark {
    border-radius: 3px;
    padding: 2px 0;
    background: var(--el-color-warning-light-7);
  }
}
</style>
