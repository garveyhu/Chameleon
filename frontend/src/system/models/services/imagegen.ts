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
  params: WorkflowParam[];
}

export const imagegenApi = {
  /** 内置生图工作流清单 —— image 模型表单按此选工作流 */
  listWorkflows: () => get<ImageWorkflow[]>('/v1/admin/imagegen/workflows'),
};
