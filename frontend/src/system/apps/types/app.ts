import type { EntityId } from '@/core/types/api';

/** key 作用域域：global=通吃 / app=某智能体 / kb=某知识库 */
export type ApiKeyScopeType = 'global' | 'app' | 'kb';

export interface ApiKeyItem {
  id: EntityId;
  /** 调用方/来源标签（自由字符串，非容器实体） */
  app_id: string;
  name: string;
  key_prefix: string;
  /** 明文 key（留存，支持重复复制；老数据为 null 只能看前缀） */
  plain_key: string | null;
  scopes: string[];
  description: string | null;
  scope_type: ApiKeyScopeType;
  scope_ref: string | null;
  qpm_limit: number | null;
  qpd_limit: number | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface CreateApiKeyRequest {
  /** 来源标签，可选；不传则后端用 name 的 slug 兜底 */
  app_id?: string;
  name: string;
  scopes?: string[];
  description?: string;
  scope_type?: ApiKeyScopeType;
  scope_ref?: string;
  qpm_limit?: number;
  qpd_limit?: number;
}

export interface ApiKeyCreated extends ApiKeyItem {
  plain_key: string; // 仅一次回显
}
