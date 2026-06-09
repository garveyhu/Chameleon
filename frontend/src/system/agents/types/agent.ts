import type { EntityId } from '@/core/types/api';

/** 轻量选项（AgentPicker 分页下拉用） */
export interface AgentOption {
  id: EntityId;
  agent_key: string;
  name: string;
  source: string;
  graph_kind: 'chatflow' | 'workflow' | null;
  icon: string | null;
}

/** Playground「关联应用」预填：按 source 尽力解析的会话默认配置 */
export interface AgentPrefillConfig {
  agent_key: string;
  name: string;
  source: string;
  graph_kind: 'chatflow' | 'workflow' | null;
  /** 是否能预填出可用配置（workflow/外部应用为 false，仅记录关联） */
  prefillable: boolean;
  model_code: string | null;
  system_prompt: string | null;
  kb_ids: EntityId[];
  /** 人类可读说明（预填范围/限制） */
  notes: string | null;
  /** 生成类应用（source=comfyui）：产物模态 + 绑定生成模型 id（前端渲染生成面板用） */
  media_kind?: 'image' | 'video' | null;
  media_model_id?: string | null;
}

export interface AgentItem {
  id: EntityId;
  agent_key: string;
  name: string;
  description: string | null;
  source: 'local' | 'dify' | 'fastgpt' | 'coze' | 'graph' | string;
  provider_id: EntityId | null;
  local_class_path: string | null;
  graph_id: EntityId | null;
  /** 关联工作流形态：chatflow / workflow（仅 source='graph' 有值），用于推导编排方式 */
  graph_kind: 'chatflow' | 'workflow' | null;
  config: Record<string, unknown> | null;
  default_model_code: string | null;
  tags: string[] | null;
  enabled: boolean;
  version: string | null;
  /** 头像 data URL（null 用默认按类型图标） */
  icon: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  agent_key: string;
  name: string;
  description?: string;
  source: 'dify' | 'fastgpt' | 'coze' | 'comfyui';
  provider_id?: EntityId;
  config?: Record<string, unknown>;
  tags?: string[];
}

export interface LinkedKbItem {
  id: EntityId;
  kb_key: string;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dim: number;
}

export interface ModelSlotItem {
  name: string;
  label: string;
  /** 此槽需要的模型类型，前端按此过滤可选模型 */
  kind: string;
  optional: boolean;
  locked: boolean;
  default: string | null;
  bound_code: string | null;
}

export interface ConfiguredModelItem {
  code: string;
  label: string;
  kind: string;
}

export interface AgentModelSlots {
  slots: ModelSlotItem[];
  models: ConfiguredModelItem[];
}

/** agentkit @agent(tools=[...]) 声明的平台工具（含启停态） */
export interface AgentToolItem {
  tool_key: string;
  description: string;
  enabled: boolean;
}

export interface AgentTools {
  tools: AgentToolItem[];
}

export interface McpServerInfo {
  name: string;
  transport: string; // stdio / http / sse
  url: string | null;
}

/** @agent 声明的安全轨道（只读） */
export interface GuardrailInfo {
  name: string; // no_injection / pii_redact / max_len / output_json_schema / 自定义
  stage: string; // input / output
  action: string; // block / redact / retry / warn
}

/** @agent 声明的高级能力（只读）：MCP / A2A / 沙箱 / durable / 记忆 / 弹性 / 安全轨道 */
export interface AgentCapabilities {
  is_local: boolean;
  mcp_servers: McpServerInfo[];
  call_agents: string[]; // A2A allow-list（agent key 或远程 URL）
  sandboxed: boolean;
  trust_tier: string; // internal / untrusted
  durable: boolean;
  working_memory: boolean; // 结构化记忆槽自动注入
  observe_memory: boolean; // observational 压缩
  retries: number; // ctx 瞬时错误退避重试次数
  guardrails: GuardrailInfo[]; // 安全轨道
}

/** durable agent 暂停中、待人工输入的 run（运营可见性） */
export interface AgentPendingRun {
  scope_ref: string; // durable scope（会话 session / end_user）
  prompt: string;
  call_index: number | null;
  run_id: string | null;
  updated_at: string;
}

export interface ConfigOptionItem {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | string;
  choices: string[] | null;
  default: unknown;
  required: boolean;
}

export interface AgentConfigSchema {
  options: ConfigOptionItem[];
  values: Record<string, unknown>;
}

/** 应用级 API 密钥（scope_type='app'，scope_ref = agent_key） */
export interface AgentApiKey {
  id: EntityId;
  name: string;
  key_prefix: string;
  /** 明文 key（留存，可重复复制；老数据为 null，只能看前缀） */
  plain_key: string | null;
  scope_type: string;
  scope_ref: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

/** 单应用调用概览（监测 tab） */
export interface AgentOverview {
  window_hours: number;
  total_calls: number;
  /** 0~1 */
  success_rate: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_duration_ms: number;
  prev_total_calls: number;
  /** 应用类型 —— 前端按此自适应指标（生成类无 token） */
  agent_source: string;
  media_kind?: 'image' | 'video' | null;
}
