import { get, post } from '@/core/lib/request';
import { streamSSE } from '@/core/lib/sse';
import type { EntityId, PageResult } from '@/core/types/api';
import type {
  AiGenStreamChunk,
  BatchDeleteItemsRequest,
  BatchDeleteItemsResult,
  BulkImportRequest,
  BulkImportResult,
  CompareRunsResult,
  CreateDatasetRequest,
  CreateDatasetRunRequest,
  CreateItemRequest,
  DatasetItem,
  DatasetItemRow,
  DatasetRunDetail,
  DatasetRunItemRow,
  DatasetRunRow,
  OptimizeResult,
  RefineCandidateRequest,
  RefinedCandidate,
  SampleFromLogsRequest,
  SamplePreviewResult,
  SampleResult,
  ScoreDistributionResult,
  UpdateItemRequest,
} from '@/system/datasets/types/dataset';

interface AiGenerateStreamOptions {
  signal?: AbortSignal;
  onChunk: (chunk: AiGenStreamChunk) => void;
}

const BASE = '/v1/admin/datasets';

export const datasetApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
    sort_by?: string;
    order?: string;
  }) => get<PageResult<DatasetItem>>(BASE, { params }),
  get: (id: EntityId) => get<DatasetItem>(`${BASE}/${id}`),
  create: (req: CreateDatasetRequest) => post<DatasetItem>(BASE, req),
  update: (id: EntityId, req: Partial<CreateDatasetRequest>) =>
    post<DatasetItem>(`${BASE}/${id}/update`, req),
  delete: (id: EntityId) => post<void>(`${BASE}/${id}/delete`),
  listItems: (id: EntityId, params?: { page?: number; page_size?: number }) =>
    get<PageResult<DatasetItemRow>>(`${BASE}/${id}/items`, { params }),
  sampleFromLogs: (id: EntityId, req: SampleFromLogsRequest) =>
    post<SampleResult>(`${BASE}/${id}/sample-from-logs`, req),
  /** 采样预览：按 filter 收集候选返回评审（不落库），挑选/编辑后再 bulkImport。 */
  previewSampleFromLogs: (id: EntityId, req: SampleFromLogsRequest) =>
    post<SamplePreviewResult>(`${BASE}/${id}/sample-from-logs/preview`, req),
  bulkImport: (id: EntityId, req: BulkImportRequest) =>
    post<BulkImportResult>(`${BASE}/${id}/items/bulk-import`, req),
  /** 流式 AI 扩样 —— SSE 边生成边吐字 + 逐条候选；不落库，候选进评审区。 */
  aiGenerateStream: (
    id: EntityId,
    body: { task_description: string; count: number },
    { signal, onChunk }: AiGenerateStreamOptions,
  ): Promise<void> =>
    streamSSE<AiGenStreamChunk>(`${BASE}/${id}/ai-generate/stream`, {
      body,
      signal,
      onChunk,
    }),
  /** 单条候选 AI 优化 / 重新生成（非流式，原地替换该卡片）。 */
  refineCandidate: (id: EntityId, req: RefineCandidateRequest) =>
    post<RefinedCandidate>(`${BASE}/${id}/ai-generate/refine`, req),
  /** H3：智能优化 —— run 低分样本 → LLM 重写 Prompt + 报告 */
  optimizeRun: (runId: EntityId) => post<OptimizeResult>(`${BASE}/runs/${runId}/optimize`, {}),
  /** H3：用优化后 Prompt 重跑整个 dataset，落新子 run（版本链） */
  applyOptimized: (runId: EntityId) =>
    post<DatasetRunDetail>(`${BASE}/runs/${runId}/apply-optimized`, {}),
  /** 人工标注：改某 item 的 expected_output / meta */
  updateItem: (itemId: EntityId, req: UpdateItemRequest) =>
    post<DatasetItemRow>(`${BASE}/items/${itemId}/update`, req),
  /** H2 电子表格「+新增行」：单条样本入库（默认 mask PII）。 */
  createItem: (datasetId: EntityId, req: CreateItemRequest) =>
    post<DatasetItemRow>(`${BASE}/${datasetId}/items/create`, req),
  /** H2 电子表格删行：删单条样本。 */
  deleteItem: (itemId: EntityId) => post<void>(`${BASE}/items/${itemId}/delete`),
  /** A2：批量删除样本（两视图删除已选 / A3 撤销采样共用），单次重算 item_count。 */
  batchDeleteItems: (datasetId: EntityId, req: BatchDeleteItemsRequest) =>
    post<BatchDeleteItemsResult>(`${BASE}/${datasetId}/items/batch-delete`, req),

  // ── runs（实验运行）—— 接出已就绪的端点 ──
  /** 可用评分器列表（judge key 数组）。 */
  listJudges: () => get<string[]>(`${BASE}/judges`),
  /** 手动发起运行（同步端点，跑完才返回，可能数十秒）。 */
  run: (id: EntityId, req: CreateDatasetRunRequest) =>
    post<DatasetRunDetail>(`${BASE}/${id}/run`, req),
  listRuns: (datasetId: EntityId) => get<DatasetRunRow[]>(`${BASE}/${datasetId}/runs`),
  /** 运行列表分页 + 名称/状态过滤（运行 tab 表格用；趋势图仍走全量 listRuns）。 */
  listRunsPaged: (
    datasetId: EntityId,
    params: { page: number; page_size: number; keyword?: string; status?: string },
  ) => get<PageResult<DatasetRunRow>>(`${BASE}/${datasetId}/runs/paged`, { params }),
  getRun: (runId: EntityId) => get<DatasetRunDetail>(`${BASE}/runs/${runId}`),
  listRunItems: (runId: EntityId) => get<DatasetRunItemRow[]>(`${BASE}/runs/${runId}/items`),
  compareRuns: (runIds: EntityId[]) =>
    post<CompareRunsResult>(`${BASE}/runs/compare`, { run_ids: runIds }),
  scoreDistribution: (runId: EntityId, threshold = 0.5, buckets = 10) =>
    get<ScoreDistributionResult>(`${BASE}/runs/${runId}/score-distribution`, {
      params: { threshold, buckets },
    }),
};
