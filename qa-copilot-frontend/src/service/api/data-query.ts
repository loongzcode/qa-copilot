import { request } from '../request';

export function fetchDataSources(projectId: number, environmentId?: number) {
  return request<Api.DataQuery.EnvironmentDataSource[]>({
    url: `/data-query/${projectId}/sources`,
    method: 'get',
    params: { environmentId }
  });
}

export function fetchCreateDataSource(projectId: number, data: Api.DataQuery.DataSourceCreateParams) {
  return request<Api.DataQuery.EnvironmentDataSource>({
    url: `/data-query/${projectId}/sources`,
    method: 'post',
    data
  });
}

export function fetchUpdateDataSource(projectId: number, sourceId: number, data: Api.DataQuery.DataSourceUpdateParams) {
  return request<Api.DataQuery.EnvironmentDataSource>({
    url: `/data-query/${projectId}/sources/${sourceId}`,
    method: 'put',
    data
  });
}

export function fetchDeleteDataSource(projectId: number, sourceId: number) {
  return request<null>({ url: `/data-query/${projectId}/sources/${sourceId}`, method: 'delete' });
}

export function fetchTestDataSource(projectId: number, sourceId: number) {
  return request<{ success: boolean; databaseVersion: string; latencyMs: number; message: string }>({
    url: `/data-query/${projectId}/sources/${sourceId}/test`,
    method: 'post'
  });
}

export function fetchRefreshDataSourceMetadata(projectId: number, sourceId: number) {
  return request<Api.DataQuery.Metadata>({
    url: `/data-query/${projectId}/sources/${sourceId}/metadata`,
    method: 'post'
  });
}

export function fetchExecuteDataQuery(
  projectId: number,
  data: { environmentId: number; dataSourceId: number; question: string }
) {
  return request<Api.DataQuery.Execution>({
    url: `/data-query/${projectId}/execute`,
    method: 'post',
    data,
    timeout: 120_000
  });
}

export function fetchDataQueryHistory(
  projectId: number,
  params: { environmentId?: number; dataSourceId?: number; current: number; size: number }
) {
  return request<Api.DataQuery.ExecutionPage>({
    url: `/data-query/${projectId}/history`,
    method: 'get',
    params
  });
}
