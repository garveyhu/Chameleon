/** 系统配置 + 模型默认 + 配置导入导出 API */

import { get, post } from '@/core/lib/request';

export interface SystemSettingItem {
  key: string;
  group: 'general' | 'session' | 'knowledge' | 'stream' | 'timeout' | 'call_log';
  value_type: 'int' | 'float' | 'bool' | 'str' | 'select';
  value: unknown;
  default: unknown;
  min: number | null;
  max: number | null;
  select_options: string[];
  description_zh: string;
  description_en: string;
}

export interface SystemSettingsResponse {
  items: SystemSettingItem[];
}

export interface ModelDefaultItem {
  case_name: 'llm' | 'embedding' | 'vision';
  model_id: number | null;
  model_code: string | null;
  model_kind: string | null;
}

export const settingsApi = {
  listSystem: () =>
    get<SystemSettingsResponse>('/v1/admin/settings/system'),
  updateSystem: (key: string, value: unknown) =>
    post<SystemSettingItem>(`/v1/admin/settings/system/${encodeURIComponent(key)}/update`, { value }),
  resetSystem: (key: string) =>
    post<SystemSettingItem>(`/v1/admin/settings/system/${encodeURIComponent(key)}/reset`),

  listModelDefaults: () =>
    get<ModelDefaultItem[]>('/v1/admin/settings/model-defaults'),
  updateModelDefault: (case_name: string, model_id: number | null) =>
    post<ModelDefaultItem>(
      `/v1/admin/settings/model-defaults/${encodeURIComponent(case_name)}/update`,
      { model_id },
    ),
};
