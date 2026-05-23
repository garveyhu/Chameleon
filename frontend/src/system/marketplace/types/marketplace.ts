import type { EntityId } from '@/core/types/api';

export interface RegistryItem {
  id: EntityId;
  registry_url: string;
  name: string;
  pubkey_pinning: Record<string, string> | null;
  enabled: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AddRegistryPayload {
  registry_url: string;
  name: string;
}

export interface UpdateRegistryPayload {
  name?: string;
  enabled?: boolean;
}

export interface MarketplaceEntry {
  registry_id: EntityId;
  registry_name: string;
  name: string;
  latest: string;
  type: 'provider' | 'tool' | 'embedding' | string;
  description: string;
  manifest_url: string;
  signature_url: string;
  publisher: string;
  tags: string[];
  downloads: number;
  updated_at: string;
  installed: boolean;
}

export interface InstallPayload {
  registry_id: EntityId;
  plugin_name: string;
}

export interface SyncResult {
  registry_id: EntityId;
  entries: number;
  publishers: number;
  last_synced_at: string;
}

export interface InstallResult {
  plugin_key: string;
  plugin_type: string;
  instance_id: number | string;
  publisher: string;
  registry: string;
}
