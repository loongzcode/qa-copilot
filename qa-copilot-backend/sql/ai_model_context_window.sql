-- 为已有 ai_models 表补充模型上下文窗口大小。
-- 该值包含系统 Prompt、历史记忆、知识库上下文、当前问题和模型输出。
ALTER TABLE ai_models
ADD COLUMN IF NOT EXISTS context_window_tokens INTEGER NOT NULL DEFAULT 32768;
