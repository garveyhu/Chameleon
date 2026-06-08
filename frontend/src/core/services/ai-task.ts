/** 系统 AI 任务 API —— 提交（带缓存）/ 轮询 / 按业务归属列出。 */

import { get, post } from '@/core/lib/request';
import type { AiTaskItem, SubmitAiTaskRequest } from '@/core/types/ai-task';
import type { EntityId } from '@/core/types/api';

const BASE = '/v1/admin/ai-tasks';

export const aiTaskApi = {
  /** 提交任务（命中缓存直接返已 success 任务，否则建 pending 后台跑）。 */
  submit: (req: SubmitAiTaskRequest) => post<AiTaskItem>(BASE, req),
  /** 轮询单个任务状态 + 结果。 */
  get: (id: EntityId) => get<AiTaskItem>(`${BASE}/${id}`),
  /** 按业务归属列历史任务（反显 / 缓存展示）。 */
  list: (params: {
    scope?: string;
    scope_ref?: string;
    task_type?: string;
    limit?: number;
  }) => get<AiTaskItem[]>(BASE, { params }),
};
