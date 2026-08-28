import { request } from '../request';

/** 查询 MCP 连接配置和当前用户有权使用的工具。 */
export function fetchGetMcpServerInfo() {
  return request<Api.McpManagement.ServerInfo>({
    url: '/mcp-management/info',
    method: 'get'
  });
}

/** 在管理页中试调用一个白名单只读工具。 */
export function fetchCallMcpTool(toolCode: string, argumentsPayload: Record<string, unknown>) {
  return request<Api.McpManagement.ToolCallResult>({
    url: `/mcp-management/tools/${encodeURIComponent(toolCode)}/call`,
    method: 'post',
    data: { arguments: argumentsPayload }
  });
}
