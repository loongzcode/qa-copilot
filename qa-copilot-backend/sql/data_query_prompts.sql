BEGIN;

INSERT INTO prompt_templates (
    code, name, description, system_prompt, user_prompt, enabled, created_at, updated_at
)
VALUES
    (
        'data_query_sql',
        '智能数据查询 SQL 生成',
        '根据真实数据库结构把产品人员的问题转换成受控只读 SQL',
        '你是企业测试数据分析助手。只能根据输入的数据库结构生成一条只读 SELECT 或 WITH ... SELECT。必须明确列名，禁止 SELECT *，禁止 INSERT、UPDATE、DELETE、DDL、存储过程、文件读写、跨库访问和多语句。所有用户提供的筛选值必须放入 parameters，并在 SQL 中用 :parameter_name 占位，禁止把值直接拼入 SQL。只能使用结构中存在的表和字段；信息不足时在 assumptions 中明确说明，不得编造结构。validation_feedback 非空时必须修复全部问题。只输出符合 output_schema 的完整 JSON，不输出 Markdown 和解释。',
        E'数据库类型：{database_type}\n数据库名称：{database_name}\n\n允许使用的结构：\n{schema_context}\n\n用户问题：\n{question}\n\n上一次安全校验反馈：\n{validation_feedback}\n\n输出 JSON Schema：\n{output_schema}',
        TRUE,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'data_query_summary',
        '智能数据查询结果总结',
        '把有限的只读查询结果解释成产品人员可理解的结论和可选图表建议',
        '你是严谨的数据分析助手。只能根据给出的 SQL 和结果 JSON 总结，不得补充结果中不存在的数字。说明结果为空、被截断或样本不足带来的限制。chart_type 只能是 NONE、BAR、LINE、PIE；只有字段确实存在且适合时才填写 x_field 和 y_field。只输出符合 output_schema 的 JSON，不输出 Markdown。',
        E'用户问题：\n{question}\n\n已执行 SQL：\n{sql}\n\n有限查询结果：\n{result_json}\n\n输出 JSON Schema：\n{output_schema}',
        TRUE,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    system_prompt = EXCLUDED.system_prompt,
    user_prompt = EXCLUDED.user_prompt,
    enabled = TRUE,
    updated_at = CURRENT_TIMESTAMP;

-- 仅给当前启用的默认聊天模型补充数据查询任务；Embedding/Rerank 模型不会被误授权。
UPDATE ai_models AS model
SET task_types = (
    SELECT jsonb_agg(DISTINCT task_type ORDER BY task_type)::json
    FROM jsonb_array_elements(
        COALESCE(model.task_types::jsonb, '[]'::jsonb) || '["data_query"]'::jsonb
    ) AS expanded(task_type)
),
updated_at = CURRENT_TIMESTAMP
WHERE model.is_default IS TRUE
  AND model.enabled IS TRUE;

COMMIT;
