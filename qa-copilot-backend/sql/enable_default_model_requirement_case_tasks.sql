-- 为当前已启用的默认聊天模型补齐需求解析与用例生成任务能力。
-- 这是运行配置，不放入通用建表脚本，避免误给新环境中的 Embedding 默认模型授权。

UPDATE ai_models AS model
SET task_types = (
    SELECT jsonb_agg(DISTINCT task_type ORDER BY task_type)::json
    FROM jsonb_array_elements(
        COALESCE(model.task_types::jsonb, '[]'::jsonb)
        || '["requirement_analysis", "coverage_analysis", "test_case_generation"]'::jsonb
    ) AS expanded(task_type)
),
updated_at = CURRENT_TIMESTAMP
WHERE model.is_default IS TRUE
  AND model.enabled IS TRUE;
