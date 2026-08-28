"""把人工测试用例转换为受控接口自动化协议。"""

from typing import Any

from pydantic import ValidationError

from app.exceptions import BadRequestException
from app.schemas.dto.automation_definitions import AutomationDefinitionSpecDTO


def build_automation_definition_from_test_case(
    test_case: Any,
) -> AutomationDefinitionSpecDTO:
    """把测试用例步骤转换成执行器唯一接受的受控定义。

    功能：读取每一步 ``test_data`` 中的 ``request``、``assertions`` 和可选
    ``extractors``，再交给 Pydantic 完整校验。
    作用：发布用例和创建自动化定义共用同一套格式规则，避免出现“发布时认为合格，
    转换时又失败”的前后端断层。
    为什么用它：自动化请求属于可执行资产，不能根据自然语言猜测接口地址或断言；
    确定性转换更安全、可审计。替代方案是模型自动补全，但必须经过人工确认后才能执行。
    """
    steps: list[dict[str, Any]] = []
    for step in sorted(test_case.steps, key=lambda item: item.step_no):
        if not isinstance(step.test_data, dict):
            raise BadRequestException(
                f"第 {step.step_no} 步缺少结构化测试数据；请点击“填入接口模板”，"
                "再修改请求方法、路径和断言"
            )
        request = step.test_data.get("request")
        assertions = step.test_data.get("assertions")
        if request is None or not assertions:
            raise BadRequestException(
                f"第 {step.step_no} 步必须提供 request（请求配置）和 "
                "assertions（结果断言）"
            )
        steps.append(
            {
                "name": step.action,
                "request": request,
                "assertions": assertions,
                "extractors": step.test_data.get("extractors", []),
            }
        )
    if not steps:
        raise BadRequestException("测试用例至少需要一个结构化接口步骤")
    try:
        return AutomationDefinitionSpecDTO.model_validate(
            {"schemaVersion": "1.0", "steps": steps}
        )
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        message = first_error.get("msg", "格式不合法")
        raise BadRequestException(
            f"自动化数据格式错误（{location}）：{message}；"
            "请在用例编辑页使用“填入接口模板”后按模板修改"
        ) from exc
