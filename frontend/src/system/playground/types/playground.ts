export type PlaygroundRole = 'user' | 'assistant' | 'system';

export interface PlaygroundMessage {
  id: string;
  role: PlaygroundRole;
  content: string;
  /** UI 标记：流式中 / 完成 / 失败 */
  status?: 'streaming' | 'done' | 'failed';
  /** assistant 完成后填的 usage */
  usage?: PlaygroundUsage | null;
  error?: string | null;
}

export interface PlaygroundUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface PlaygroundParams {
  model_id?: number;
  model_name?: string;
  system_prompt: string;
  temperature: number;
  top_p: number | null;
  max_tokens: number | null;
  kb_ids: number[];
}

export interface InvokeRequest {
  model_id?: number;
  model_name?: string;
  system_prompt?: string;
  temperature: number;
  top_p?: number | null;
  max_tokens?: number | null;
  messages: Array<{ role: PlaygroundRole; content: string }>;
  kb_ids?: number[];
}

export interface InvokeChunk {
  delta?: string;
  end?: boolean;
  usage?: PlaygroundUsage | null;
  error?: { type: string; message: string };
}
