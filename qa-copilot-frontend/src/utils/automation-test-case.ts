/** 将测试类型内部编码转换为用户可读的中文。 */
export function getTestCaseTypeLabel(caseType: Api.RequirementManage.TestCaseType) {
  return {
    FUNCTIONAL: '功能测试',
    API: '接口测试',
    UI: '界面测试',
    PERFORMANCE: '性能测试',
    SECURITY: '安全测试',
    COMPATIBILITY: '兼容性测试',
    REGRESSION: '回归测试',
    SMOKE: '冒烟测试',
    OTHER: '其他测试'
  }[caseType];
}

/** 判断每个步骤是否至少具备受控接口请求和结果断言。 */
export function hasStructuredAutomationSteps(testCase: Api.RequirementManage.TestCase) {
  return (
    testCase.steps.length > 0 &&
    testCase.steps.every(step => {
      if (!step.testData || typeof step.testData !== 'object' || Array.isArray(step.testData)) return false;
      const testData = step.testData as Record<string, unknown>;
      return (
        Boolean(testData.request) &&
        typeof testData.request === 'object' &&
        !Array.isArray(testData.request) &&
        Array.isArray(testData.assertions) &&
        testData.assertions.length > 0
      );
    })
  );
}

/** 返回用例不能进入接口自动化模块的直接原因；空字符串表示基础条件满足。 */
export function getAutomationIneligibleReason(testCase: Api.RequirementManage.TestCase) {
  if (testCase.caseType !== 'API') return `类型为${getTestCaseTypeLabel(testCase.caseType)}，不是接口测试`;
  if (!testCase.automatable) return '未标记为可自动化';
  if (!hasStructuredAutomationSteps(testCase)) return '步骤缺少结构化 request 或 assertions';
  return '';
}

/** 生成可直接编辑的最小接口自动化步骤模板。 */
export function createAutomationStepTemplateText() {
  return JSON.stringify(
    {
      request: {
        method: 'GET',
        path: '/api/example',
        headers: {},
        query: {},
        timeoutSeconds: 30
      },
      assertions: [{ type: 'STATUS_CODE', expected: 200 }],
      extractors: []
    },
    null,
    2
  );
}
