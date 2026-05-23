import type { EntityId } from '@/core/types/api';

export type PluginType = 'provider' | 'tool' | 'embedding';
export type PluginSource = 'builtin' | 'local' | 'git' | 'pypi';

export interface PluginPermissions {
  network?: boolean;
  filesystem?: boolean;
}

export interface PluginConfigField {
  type?: 'string' | 'int' | 'float' | 'bool';
  required?: boolean;
  sensitive?: boolean;
  default?: unknown;
  description?: string;
  enum?: unknown[];
}

export interface PluginManifest {
  name: string;
  version: string;
  type: PluginType;
  entrypoint: string;
  chameleon_version?: string;
  description?: string | null;
  config_schema?: Record<string, PluginConfigField>;
  permissions?: PluginPermissions;
}

export interface PluginInstanceItem {
  id: EntityId;
  plugin_key: string;
  name: string;
  type: PluginType;
  version: string;
  source: PluginSource;
  source_url: string | null;
  manifest: PluginManifest;
  config: Record<string, unknown>;
  enabled: boolean;
  installed_at: string;
  updated_at: string;
}

export interface InstallPluginPayload {
  manifest: PluginManifest;
  source: 'local' | 'git' | 'pypi';
  source_url?: string | null;
  config?: Record<string, unknown>;
}

export interface PluginActionResult {
  plugin_key: string;
  enabled: boolean;
  loaded: boolean;
  message: string | null;
}

/** 安装弹窗里 plugin type 下拉 */
export const PLUGIN_TYPE_OPTIONS: { label: string; value: PluginType }[] = [
  { label: 'Provider（外部 LLM/Agent 接入）', value: 'provider' },
  { label: 'Tool（function calling 工具）', value: 'tool' },
  { label: 'Embedding（向量化模型）', value: 'embedding' },
];

export const PLUGIN_SOURCE_OPTIONS: { label: string; value: 'local' | 'git' | 'pypi' }[] = [
  { label: 'Local（venv 已 pip 安装）', value: 'local' },
  { label: 'Git URL', value: 'git' },
  { label: 'PyPI', value: 'pypi' },
];
