declare namespace Api {
  /** Model Context Protocol（模型上下文协议）管理接口。 */
  namespace McpManagement {
    type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

    type JsonSchemaProperty = {
      type?: string;
      title?: string;
      description?: string;
      default?: unknown;
      enum?: Array<string | number>;
      anyOf?: JsonSchemaProperty[];
      $ref?: string;
    };

    type InputSchema = {
      type?: string;
      properties?: Record<string, JsonSchemaProperty>;
      required?: string[];
      $defs?: Record<string, JsonSchemaProperty>;
    };

    type Tool = {
      code: string;
      name: string;
      description: string;
      riskLevel: RiskLevel;
      requiredPermission: string;
      readOnly: boolean;
      inputSchema: InputSchema;
    };

    type ServerInfo = {
      enabled: boolean;
      endpoint: string;
      transport: string;
      authScheme: string;
      tools: Tool[];
    };

    type ToolCallResult = {
      toolCode: string;
      result: Record<string, unknown>;
    };
  }
}
