import type { EntityId } from '@/core/types/api';

export type AppTemplateCategory = 'assistant' | 'agent' | 'workflow' | 'rag';

export interface AppTemplateItem {
  id: EntityId;
  name: string;
  description: string | null;
  category: AppTemplateCategory | string;
  spec_json: Record<string, unknown>;
  cover_image: string | null;
  verified: boolean;
  downloads: number;
  created_by_user_id: EntityId | null;
  workspace_id: EntityId | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAppTemplateRequest {
  name: string;
  description?: string;
  category: AppTemplateCategory;
  spec_json: Record<string, unknown>;
  cover_image?: string;
}

export interface InstallTemplateResult {
  template_id: EntityId;
  template_name: string;
  category: string;
  target_workspace_id: EntityId | null;
  installed_at: string;
  artifact_id: EntityId | null;
}
