-- 需求覆盖分析与缺失用例生成增量升级。
-- 本文件可重复执行：Prompt 使用 ON CONFLICT，索引使用 IF NOT EXISTS。

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS ix_test_cases_search_trgm
    ON test_cases
    USING gin (((coalesce(title, '') || ' ' || coalesce(preconditions, '') || ' '
        || coalesce(expected_summary, ''))) gin_trgm_ops);

DROP INDEX IF EXISTS uq_case_generation_tasks_active_requirement;
CREATE UNIQUE INDEX uq_case_generation_tasks_active_requirement
    ON case_generation_tasks(requirement_id)
    WHERE status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW');

INSERT INTO prompt_templates (
    code, name, description, system_prompt, user_prompt, enabled, created_at, updated_at
)
VALUES
    (
        'coverage_analysis',
        '需求覆盖分析',
        '判断已发布标准用例对已确认原子需求点的覆盖程度',
        '你是资深测试架构师。根据已确认需求点和系统提供的候选标准用例，判断候选用例是否完全覆盖 FULL 或部分覆盖 PARTIAL。没有覆盖关系的组合不要输出。判断必须同时考虑前置条件、操作步骤、测试数据、业务规则、边界和预期结果；标题相似不等于覆盖。requirement_item_id 与 test_case_id 只能使用输入中真实存在且互相允许的组合。reason、covered_aspects、missing_aspects 要具体、可供人工复核。严格按照 JSON Schema 输出完整 JSON，不要输出 Markdown 或解释。validation_feedback 非空时修复全部问题。',
        E'输出 JSON Schema：\n{output_schema}\n\n上次校验反馈：\n{validation_feedback}\n\n需求点：\n{requirements_json}\n\n候选标准用例：\n{candidate_cases_json}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    ),
    (
        'test_case_generation',
        '缺失测试用例生成',
        '只针对部分覆盖或未覆盖的需求点生成可审核测试用例草稿',
        '你是资深测试设计专家。只为 coverage_gaps_json 中的覆盖缺口生成必要且不重复的测试用例。每条用例必须至少关联一个输入中的 requirement_item_id，并包含明确标题、前置条件、连续步骤、测试数据和可验证预期。优先补齐部分覆盖中的 missing_aspects，并覆盖正常、异常、边界、权限等适用场景。reference_cases_json 只能作为风格、业务和判重参考，source_case_ids 只能引用其中真实 ID，禁止照抄或生成语义重复用例。不得引用未提供 ID，不得直接发布。严格按 JSON Schema 输出完整 JSON，不要输出 Markdown 或解释。validation_feedback 非空时修复全部问题后重新输出。',
        E'输出 JSON Schema：\n{output_schema}\n\n上次校验反馈：\n{validation_feedback}\n\n待补覆盖缺口：\n{coverage_gaps_json}\n\n历史标准用例参考：\n{reference_cases_json}',
        true,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    system_prompt = EXCLUDED.system_prompt,
    user_prompt = EXCLUDED.user_prompt,
    enabled = true,
    updated_at = CURRENT_TIMESTAMP;
