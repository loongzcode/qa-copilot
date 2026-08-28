BEGIN;

-- 为现有环境补充需求拆解内置 Prompt。若管理员已在后台创建同编码模板，
-- ON CONFLICT DO NOTHING 会保留已有内容，不覆盖人工调整结果。
INSERT INTO prompt_templates (
    code,
    name,
    description,
    system_prompt,
    user_prompt,
    enabled,
    created_at,
    updated_at
)
VALUES (
    'requirement_analysis',
    'AI 需求拆解',
    '把需求正文拆解为可人工校正和确认的原子需求点',
    '你是资深测试分析师。请忠于需求原文，把内容拆解为边界清晰、可独立验收的原子需求点。local_id 在本次输出内必须唯一；parent_local_id 只能引用本次输出中的 local_id，顶层需求填 null，禁止形成循环。文档正文包含 SOURCE 标记时，source_chunk_ids 只能引用标记中真实存在的 chunk_id；没有 SOURCE 标记时必须返回空列表。source_quote 只摘录支撑当前需求点的短原文。不得编造需求、来源、规则或验收条件；原文存在歧义、冲突或信息不足时写入 warnings。严格按照给定 JSON Schema 输出一个完整 JSON 对象，不要输出 Markdown 代码块、解释文字或 JSON 之外的内容。validation_feedback 非空时，修正其中所有问题后重新输出完整结果。',
    E'目标 JSON Schema：\n{output_schema}\n\n上一次校验反馈：\n{validation_feedback}\n\n待拆解需求正文：\n{requirement_text}',
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
)
ON CONFLICT (code) DO NOTHING;

COMMIT;
