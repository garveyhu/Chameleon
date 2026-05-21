export interface ModelItem {
  id: number;
  provider_id: number;
  provider_code: string | null;
  code: string;
  kind: 'chat' | 'embedding';
  dim: number | null;
  defaults: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateModelRequest {
  provider_id: number;
  code: string;
  kind: 'chat' | 'embedding';
  dim?: number;
  defaults?: Record<string, unknown>;
}
