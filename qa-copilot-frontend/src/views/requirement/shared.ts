export const requirementStatusOptions: Array<{
  label: string;
  value: Api.RequirementManage.RequirementStatus;
}> = [
  { label: '草稿', value: 'DRAFT' },
  { label: '拆解中', value: 'EXTRACTING' },
  { label: '待确认', value: 'REVIEWING' },
  { label: '已确认', value: 'CONFIRMED' },
  { label: '拆解失败', value: 'FAILED' },
  { label: '已归档', value: 'ARCHIVED' }
];

export const requirementItemTypeOptions: Array<{
  label: string;
  value: Api.RequirementManage.RequirementItemType;
}> = [
  { label: '功能需求', value: 'FUNCTIONAL' },
  { label: '业务规则', value: 'BUSINESS_RULE' },
  { label: '正常流程', value: 'NORMAL_FLOW' },
  { label: '异常流程', value: 'EXCEPTION_FLOW' },
  { label: '边界条件', value: 'BOUNDARY' },
  { label: '权限要求', value: 'PERMISSION' },
  { label: '性能要求', value: 'PERFORMANCE' },
  { label: '安全要求', value: 'SECURITY' },
  { label: '兼容性要求', value: 'COMPATIBILITY' },
  { label: '其他', value: 'OTHER' }
];

export const priorityOptions: Array<{ label: string; value: Api.RequirementManage.Priority }> = [
  { label: 'P0 最高', value: 'P0' },
  { label: 'P1 高', value: 'P1' },
  { label: 'P2 中', value: 'P2' },
  { label: 'P3 低', value: 'P3' }
];

export const testCaseTypeOptions: Array<{ label: string; value: Api.RequirementManage.TestCaseType }> = [
  { label: '功能测试', value: 'FUNCTIONAL' },
  { label: '接口测试', value: 'API' },
  { label: 'UI 测试', value: 'UI' },
  { label: '性能测试', value: 'PERFORMANCE' },
  { label: '安全测试', value: 'SECURITY' },
  { label: '兼容性测试', value: 'COMPATIBILITY' },
  { label: '回归测试', value: 'REGRESSION' },
  { label: '冒烟测试', value: 'SMOKE' },
  { label: '其他', value: 'OTHER' }
];

export function requirementStatusLabel(status: Api.RequirementManage.RequirementStatus) {
  return requirementStatusOptions.find(item => item.value === status)?.label ?? status;
}

export function requirementStatusType(status: Api.RequirementManage.RequirementStatus) {
  const typeMap: Record<
    Api.RequirementManage.RequirementStatus,
    'info' | 'primary' | 'warning' | 'success' | 'danger'
  > = {
    DRAFT: 'info',
    EXTRACTING: 'primary',
    REVIEWING: 'warning',
    CONFIRMED: 'success',
    FAILED: 'danger',
    ARCHIVED: 'info'
  };
  return typeMap[status];
}

export function requirementItemTypeLabel(type: Api.RequirementManage.RequirementItemType) {
  return requirementItemTypeOptions.find(item => item.value === type)?.label ?? type;
}

export function flattenModules(
  modules: Api.ProjectManage.ProjectModule[],
  depth = 0
): Array<{ id: number; name: string }> {
  return modules.flatMap(module => [
    { id: module.id, name: `${'　'.repeat(depth)}${module.name}` },
    ...flattenModules(module.children || [], depth + 1)
  ]);
}
