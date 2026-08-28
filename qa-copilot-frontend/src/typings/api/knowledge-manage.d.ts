declare namespace Api {
  /** 测试知识库管理接口。 */
  namespace KnowledgeManage {
    type Visibility = 'PROJECT' | 'MANAGERS' | 'PRIVATE';
    type ModelTaskType = 'embedding' | 'rerank';

    type KnowledgeBase = {
      id: number;
      projectId: number;
      name: string;
      description: string;
      visibility: Visibility;
      embeddingModelId: number;
      embeddingModelName: string;
      rerankModelId: number | null;
      rerankModelName: string | null;
      documentCount: number;
      chunkCount: number;
      enabled: boolean;
      createdBy: number | null;
      createdByName: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type KnowledgeBaseSearchParams = {
      current: number;
      size: number;
      keyword: string;
      enabled?: boolean;
    };

    type KnowledgeBaseCreateParams = {
      name: string;
      description: string;
      visibility: Visibility;
      embeddingModelId: number;
      rerankModelId: number | null;
      enabled: boolean;
    };

    type KnowledgeBaseUpdateParams = Partial<KnowledgeBaseCreateParams>;
    type KnowledgeBaseList = Common.PaginatingQueryRecord<KnowledgeBase>;

    type KnowledgeDocumentType =
      | 'STANDARD_CASE'
      | 'TEST_PROCESS'
      | 'OPERATION_GUIDE'
      | 'SYSTEM_DESIGN'
      | 'REQUIREMENT'
      | 'API_DOCUMENT'
      | 'DEFECT_EXPERIENCE'
      | 'OTHER';

    type KnowledgeDocumentParseStatus = 'PENDING' | 'PARSING' | 'INDEXING' | 'READY' | 'FAILED';
    type KnowledgeDocumentSourceType = 'UPLOAD' | 'URL' | 'MANUAL' | 'IMPORT';

    type KnowledgeDocument = {
      id: number;
      knowledgeBaseId: number;
      moduleId: number | null;
      moduleName: string | null;
      documentType: KnowledgeDocumentType;
      title: string;
      sourceType: KnowledgeDocumentSourceType;
      sourceUrl: string | null;
      originalFilename: string | null;
      mimeType: string | null;
      sizeBytes: number | null;
      sha256: string | null;
      version: number;
      parseStatus: KnowledgeDocumentParseStatus;
      errorMessage: string | null;
      metadata: Record<string, unknown>;
      chunkCount: number;
      createdBy: number | null;
      createdByName: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type KnowledgeDocumentSearchParams = {
      current: number;
      size: number;
      keyword: string;
      documentType?: KnowledgeDocumentType;
      parseStatus?: KnowledgeDocumentParseStatus;
      moduleId?: number;
    };

    type KnowledgeDocumentUploadParams = {
      title?: string;
      documentType: KnowledgeDocumentType;
      moduleId?: number;
      metadata?: Record<string, unknown>;
      file: File;
    };

    type KnowledgeDocumentList = Common.PaginatingQueryRecord<KnowledgeDocument>;

    type ModelOption = {
      id: number;
      name: string;
      modelId: string;
      providerName: string;
    };

    type KnowledgeChatParams = {
      query: string;
      topK?: number;
      moduleId?: number;
      documentTypes?: KnowledgeDocumentType[];
    };

    type KnowledgeChatSessionStatus = 'ACTIVE' | 'ARCHIVED';
    type KnowledgeChatMessageRole = 'USER' | 'ASSISTANT';
    type KnowledgeChatMessageStatus = 'PENDING' | 'SUCCESS' | 'FAILED';

    type KnowledgeCitation = {
      sourceNumber: number;
      chunkId: number;
      documentId: number;
      documentTitle: string;
      moduleId: number | null;
      moduleName: string | null;
      chunkIndex: number;
      sectionTitle: string | null;
      pageNo: number | null;
      content: string;
      score: number;
    };

    type KnowledgeChatSession = {
      id: number;
      projectId: number;
      knowledgeBaseId: number;
      userId: number;
      userName: string | null;
      title: string;
      status: KnowledgeChatSessionStatus;
      lastMessageAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type KnowledgeChatSessionList = Common.PaginatingQueryRecord<KnowledgeChatSession>;

    type KnowledgeChatSessionCreateParams = {
      title?: string;
    };

    type KnowledgeChatSessionUpdateParams = {
      title?: string;
      status?: KnowledgeChatSessionStatus;
    };

    type KnowledgeChatSessionSearchParams = {
      current: number;
      size: number;
      status?: KnowledgeChatSessionStatus;
    };

    type KnowledgeChatMessage = {
      id: number;
      sessionId: number;
      role: KnowledgeChatMessageRole;
      content: string;
      citations: KnowledgeCitation[];
      modelId: number | null;
      promptTemplateId: number | null;
      status: KnowledgeChatMessageStatus;
      tokenCount: number;
      errorMessage: string | null;
      createdAt: string;
    };

    type KnowledgeChatMessageCursor = {
      records: KnowledgeChatMessage[];
      hasMore: boolean;
      nextCursor: number | null;
    };

    type KnowledgeChatMessageCursorParams = {
      beforeId?: number;
      limit?: number;
    };

    type KnowledgeChatAuditSearchParams = {
      current: number;
      size: number;
      knowledgeBaseId?: number;
      userId?: number;
      status?: KnowledgeChatSessionStatus;
    };

    type KnowledgeChatSendResult = {
      userMessage: KnowledgeChatMessage;
      assistantMessage: KnowledgeChatMessage;
    };

    /** 知识问答流式处理阶段。 */
    type KnowledgeChatStreamStage =
      | 'SAVING'
      | 'REWRITING'
      | 'RETRIEVING'
      | 'RERANKING'
      | 'GENERATING'
      | 'SAVING_RESULT';

    type KnowledgeChatStreamStatus = {
      stage: KnowledgeChatStreamStage;
      message: string;
    };

    type KnowledgeChatStreamDelta = {
      content: string;
    };

    type KnowledgeChatStreamCitations = {
      citations: KnowledgeCitation[];
    };

    type KnowledgeChatStreamError = {
      message: string;
      assistantMessage: KnowledgeChatMessage | null;
    };

    /** 原生 fetch 读取 SSE 时，各事件交给页面处理的回调。 */
    type KnowledgeChatStreamHandlers = {
      onStatus?: (data: KnowledgeChatStreamStatus) => void;
      onDelta?: (data: KnowledgeChatStreamDelta) => void;
      onCitations?: (data: KnowledgeChatStreamCitations) => void;
      onDone?: (data: KnowledgeChatSendResult) => void;
      onError?: (data: KnowledgeChatStreamError) => void;
    };
  }
}
