export interface OverviewItem {
  total_calls_24h: number;
  total_calls_7d: number;
  success_rate_24h: number;
  avg_duration_ms_24h: number;
  total_prompt_tokens_24h: number;
  total_completion_tokens_24h: number;
  active_apps_24h: number;
  active_agents_24h: number;
  range_from?: string | null;
  range_to?: string | null;
  total_calls_in_range?: number;
  prev_period_calls?: number;
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

export interface TopAgent {
  agent_key: string;
  count: number;
}

export interface TopApp {
  app_id: string;
  count: number;
}
