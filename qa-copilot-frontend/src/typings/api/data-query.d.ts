declare namespace Api {
  /** 测试环境智能数据查询接口。 */
  namespace DataQuery {
    type DatabaseType = 'MYSQL' | 'POSTGRESQL';
    type ExecutionStatus = 'GENERATING' | 'VALIDATING' | 'EXECUTING' | 'SUCCEEDED' | 'REJECTED' | 'FAILED';

    type EnvironmentDataSource = {
      id: number;
      projectId: number;
      environmentId: number;
      name: string;
      databaseType: DatabaseType;
      host: string;
      port: number;
      databaseName: string;
      schemaName: string | null;
      sslEnabled: boolean;
      charset: string;
      allowedTables: string[];
      sensitiveColumns: Record<string, string[]>;
      credentialsConfigured: boolean;
      enabled: boolean;
      metadataTableCount: number;
      metadataCapturedAt: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type DataSourceCreateParams = {
      environmentId: number;
      name: string;
      databaseType: DatabaseType;
      host: string;
      port?: number;
      databaseName: string;
      schemaName?: string | null;
      username: string;
      password: string;
      sslEnabled: boolean;
      charset: string;
      allowedTables: string[];
      sensitiveColumns: Record<string, string[]>;
      enabled: boolean;
    };

    type DataSourceUpdateParams = Partial<Omit<DataSourceCreateParams, 'environmentId' | 'databaseType'>>;

    type Metadata = {
      dataSourceId: number;
      databaseType: DatabaseType;
      databaseName: string;
      schemaName: string | null;
      tables: Array<{
        name: string;
        comment: string;
        columns: Array<{
          name: string;
          type: string;
          nullable: boolean;
          primaryKey: boolean;
          comment: string;
        }>;
        foreignKeys: Array<{
          column: string;
          referencedTable: string;
          referencedColumn: string;
        }>;
      }>;
      tableCount: number;
      capturedAt: string;
    };

    type Execution = {
      id: number;
      projectId: number;
      environmentId: number;
      dataSourceId: number;
      dataSourceName: string;
      userId: number | null;
      question: string;
      status: ExecutionStatus;
      sqlDialect: string;
      generatedSql: string | null;
      parameters: Record<string, unknown>;
      referencedTables: string[];
      validationErrors: string[];
      resultColumns: string[];
      resultRows: Array<Record<string, unknown>>;
      resultRowCount: number;
      truncated: boolean;
      summary: string;
      visualization: {
        chartType?: 'NONE' | 'BAR' | 'LINE' | 'PIE';
        xField?: string | null;
        yField?: string | null;
        insights?: string[];
      };
      estimatedRows: number | null;
      fullTableScan: boolean;
      latencyMs: number;
      errorMessage: string | null;
      createdAt: string;
      updatedAt: string;
    };

    type ExecutionPage = Common.PaginatingQueryRecord<Execution>;
  }
}
