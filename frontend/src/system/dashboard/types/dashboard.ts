/** dashboard 类型 —— 与后端 schemas.py 镜像
 *
 * 指标统一区间口径（不再有 *_24h 字段）；雪花类 id（session_id/user_id）一律 string。
 */

export type DimensionKey =
  | 'agent_key'
  | 'app_id'
  | 'session_id'
  | 'user_id'
  | 'end_user_id'
  | 'model_code'
  | 'channel'
  | 'error_class';

export interface OverviewItem {
  range_from: string;
  range_to: string;
  // 流量
  total_calls: number;
  prev_period_calls: number;
  // 健康
  success_rate: number;
  prev_success_rate: number | null;
  avg_duration_ms: number;
  // token
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  // 活跃实体
  active_apps: number;
  active_agents: number;
  active_end_users: number;
  // 流式占比
  stream_ratio: number;
  /** P95 响应延迟（仅 PG；测试库为 null） */
  p95_duration_ms: number | null;
  /** 首字延迟（avg completion_start_ms，无则 null） */
  ttft_avg_ms: number | null;
}

export interface TimePoint {
  ts: string;
  total: number;
  errors: number;
}

export interface TimeSeriesResult {
  granularity: 'hour' | 'day';
  points: TimePoint[];
}

export interface TopDimensionRow {
  label: string;
  display_name?: string | null;
  count: number;
}

export interface CostTotalsResult {
  range_from: string;
  range_to: string;
  total_usd: number;
  prev_total_usd: number | null;
  delta_pct: number | null;
  total_calls: number;
  total_tokens: number;
}

export interface CostDimensionRow {
  label: string;
  display_name?: string | null;
  cost_usd: number;
  calls: number;
  success_calls: number;
  total_tokens: number;
}

export interface CostTimeseriesPoint {
  ts: string;
  cost_usd: number;
  total_tokens: number;
}

export interface DistributionRow {
  label: string;
  display_name?: string | null;
  count: number;
  cost_usd: number;
}
