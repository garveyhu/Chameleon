/** 系统 AI 任务（异步执行 + 状态跟踪 + 结果缓存）。后端 ai_tasks 域。 */

import type { EntityId } from '@/core/types/api';

export type AiTaskStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'cancelled';

export interface AiTaskItem {
  id: EntityId;
  task_type: string;
  scope: string | null;
  scope_ref: string | null;
  status: AiTaskStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  model_code: string | null;
  total_tokens: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SubmitAiTaskRequest {
  task_type: string;
  scope?: string;
  scope_ref?: string;
  input?: Record<string, unknown>;
  /** 跳过缓存强制新建（默认命中同输入的 success 任务直接复用） */
  force?: boolean;
}
