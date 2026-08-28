-- 强化知识问答的回答范围边界，避免模型把相邻业务一起展开。
-- `POSITION` 判断使脚本可以重复执行，不会重复追加同一条规则。
UPDATE prompt_templates
SET system_prompt = system_prompt || E'\n\n11. 回答范围边界：\n'
    || E'   - 回答前先识别用户限定的业务对象、系统、阶段和问题类型，只保留直接回答该问题必需的内容。\n'
    || E'   - 不得因为候选资料中存在相邻业务就主动扩展。例如：还款和扣款问题不得扩展代偿；只问 CBS 时不得扩展 CAP。\n'
    || E'   - 与用户当前问题无直接关系的候选资料，不得写入正文，也不得生成对应引用。\n'
    || E'   - 完成直接回答后立即停止，除非用户明确要求，不添加“另外”、“相关内容”或额外扩展章节。',
    updated_at = CURRENT_TIMESTAMP
WHERE code = 'rag_answer'
  AND POSITION('11. 回答范围边界：' IN system_prompt) = 0;

-- 保留用户明确询问的物理表名、字段名等技术标识符。
UPDATE prompt_templates
SET system_prompt = system_prompt || E'\n\n12. 精确技术标识符：\n'
    || E'   - 用户询问“哪张表、哪个字段、哪个接口、哪个调度或哪个配置键”时，必须保留上下文中对应的完整技术标识符。\n'
    || E'   - 技术标识符使用反引号包裹，不得只输出中文业务名称来代替物理名称。\n'
    || E'   - 上下文没有给出精确标识符时，明确说明资料不足，不得自行猜测名称。',
    updated_at = CURRENT_TIMESTAMP
WHERE code = 'rag_answer'
  AND POSITION('12. 精确技术标识符：' IN system_prompt) = 0;

-- 让回答粒度与问题粒度保持一致，避免“问配置却顺带回答执行流程”。
UPDATE prompt_templates
SET system_prompt = system_prompt || E'\n\n13. 问题粒度约束：\n'
    || E'   - 用户只询问配置、表、字段、接口或调度名称时，仅回答对应标识符及理解它所必需的说明。\n'
    || E'   - 除非用户同时询问操作方法，否则不得主动补充前置条件、后续执行步骤或相邻流程。\n'
    || E'   - 引用只保留直接支撑当前答案的资料，不得引用仅支撑被省略扩展内容的资料。',
    updated_at = CURRENT_TIMESTAMP
WHERE code = 'rag_answer'
  AND POSITION('13. 问题粒度约束：' IN system_prompt) = 0;
