import type { EntityId } from '@/core/types/api';

export type KbChunkMode = 'fixed' | 'paragraph' | 'sentence' | 'regex' | 'token';

export interface KbChunkStrategy {
  mode: KbChunkMode;
  chunk_size?: number;
  overlap?: number;
  separator_regex?: string;
  /** token 模式：编码器锚定模型（缺省走 cl100k_base） */
  model?: string;
}

export interface KbItem {
  id: EntityId;
  kb_key: string;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dim: number;
  chunk_size: number;
  chunk_overlap: number;
  chunk_strategy: KbChunkStrategy | null;
  default_top_k: number;
  recall_mode: 'vector' | 'hybrid' | 'keyword';
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChunkItem {
  id: EntityId;
  doc_id: EntityId;
  seq: number;
  content: string;
  token_count: number | null;
  meta: Record<string, unknown> | null;
  enabled: boolean;
  keywords: string[] | null;
  hit_count: number;
  created_at: string;
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface DocumentItem {
  id: EntityId;
  kb_id: EntityId;
  title: string;
  source_type: 'upload' | 'url' | 'text';
  source_uri: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  status: DocumentStatus;
  status_message: string | null;
  chunk_count: number;
  token_count: number;
  enabled: boolean;
  tags: string[];
  chunk_strategy: KbChunkStrategy | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatusInfo {
  document_id: EntityId;
  status: DocumentStatus;
  progress: number;
  message: string | null;
  chunk_count: number;
  token_count: number;
  task_id: EntityId | null;
}

export interface IngestQueued {
  document_id: EntityId;
  task_id: EntityId;
}

export type RecallMode = 'vector' | 'hybrid' | 'keyword';

export interface SearchRequest {
  query: string;
  top_k?: number;
  min_score?: number;
  doc_ids?: EntityId[];
  tags?: string[];
  mode?: RecallMode;
  /** B1：multi-query 扩展变体数（后端接入后生效） */
  multi_query_count?: number;
}

export interface SearchHitItem {
  chunk_id: EntityId;
  doc_id: EntityId;
  seq: number;
  content: string;
  /** 综合得分（融合后） */
  score: number;
  document_title: string;
  /** B6 score breakdown 分项（后端接入后返回；缺省即未启用对应通道） */
  vector_score?: number | null;
  bm25_score?: number | null;
  rerank_score?: number | null;
}
