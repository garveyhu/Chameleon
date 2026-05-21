export interface CallLogItem {
  id: number;
  request_id: string;
  app_id: string;
  agent_key: string;
  api_key_id: number | null;
  session_id: string | null;
  stream: boolean;
  success: boolean;
  code: number;
  error_class: string | null;
  error_message: string | null;
  duration_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  created_at: string;
}
