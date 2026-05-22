import type { EntityId } from '@/core/types/api';

export type ChannelStatus = 'enabled' | 'auto_disabled' | 'manual_disabled';

export interface ChannelItem {
  id: EntityId;
  provider_id: EntityId;
  provider_code: string | null;
  name: string;
  has_api_key: boolean;
  base_url: string | null;
  status: ChannelStatus;
  weight: number;
  priority: number;
  response_time_ms: number | null;
  fail_count: number;
  used_quota: number;
  last_failed_at: string | null;
  last_success_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateChannelRequest {
  provider_id: EntityId;
  name: string;
  api_key?: string;
  base_url?: string;
  weight?: number;
  priority?: number;
}

export interface UpdateChannelRequest {
  name?: string;
  /** 非空才更新；空字符串 → 清空 */
  api_key?: string;
  base_url?: string;
  status?: ChannelStatus;
  weight?: number;
  priority?: number;
}
