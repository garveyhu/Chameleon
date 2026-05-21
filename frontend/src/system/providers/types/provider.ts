export interface ProviderItem {
  id: number;
  code: string;
  kind: 'llm' | 'embedding' | 'dify' | 'fastgpt' | 'coze';
  name: string;
  base_url: string | null;
  has_api_key: boolean;
  extra_config: Record<string, unknown> | null;
  enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateProviderRequest {
  code: string;
  kind: ProviderItem['kind'];
  name: string;
  base_url?: string;
  api_key?: string;
  extra_config?: Record<string, unknown>;
  description?: string;
}
