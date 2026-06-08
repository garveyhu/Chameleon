import type { EntityId } from '@/core/types/api';
import { get } from '@/core/lib/request';

export interface WorkflowParam {
  key: string;
  label: string;
  type: string;
  default?: unknown;
}

export interface ImageWorkflow {
  id: string;
  name: string;
  description: string;
  /** t2i 文生图 / i2i 图生图 —— 配置面板按此分组到对应工作流下拉 */
  task: string;
  params: WorkflowParam[];
}

/** 生成面板的一个可调参数字段（声明式，后端按模型/驱动给出） */
export interface ParamField {
  key: string;
  label: string;
  type: 'aspect_ratio' | 'select' | 'int' | 'float' | 'text' | 'seed' | 'toggle';
  default?: unknown;
  group: 'basic' | 'advanced';
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  /** aspect_ratio 字段：除预置比例外是否允许自定义宽高 */
  custom?: boolean;
}

export interface StylePreset {
  id: string;
  label: string;
  suffix: string;
}

export interface MediaParamSpec {
  media_kind: 'image' | 'video';
  fields: ParamField[];
  styles: StylePreset[];
  /** 该模型是否支持图生图（配了 edit_workflow）—— 决定是否显示参考图上传 */
  supports_i2i: boolean;
}

export const imagegenApi = {
  /** 内置生图工作流清单 —— image 模型表单按此选工作流 */
  listWorkflows: () => get<ImageWorkflow[]>('/v1/admin/imagegen/workflows'),
  /** 媒体模型可调参数规约 + 风格预设 —— 生成面板动态渲染 */
  getParamSpec: (modelId: EntityId) =>
    get<MediaParamSpec>('/v1/admin/imagegen/param-spec', { params: { model_id: modelId } }),
};
