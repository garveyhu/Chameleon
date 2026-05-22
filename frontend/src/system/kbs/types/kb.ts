export interface KbChunkStrategy {
  mode: 'fixed' | 'paragraph' | 'sentence' | 'regex';
  chunk_size?: number;
  overlap?: number;
  separator_regex?: string;
}

export interface KbItem {
  id: number;
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
  id: number;
  doc_id: number;
  seq: number;
  content: string;
  token_count: number | null;
  meta: Record<string, unknown> | null;
  created_at: string;
}

export type DocumentStatus =
  | 'pending'
  | 'processing'
  | 'ready'
  | 'failed';

export interface DocumentItem {
  id: number;
  kb_id: number;
  title: string;
  source_type: 'upload' | 'url' | 'text';
  source_uri: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  status: DocumentStatus;
  status_message: string | null;
  chunk_count: number;
  token_count: number;
  tags: string[];
  chunk_strategy: KbChunkStrategy | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatusInfo {
  document_id: number;
  status: DocumentStatus;
  progress: number;
  message: string | null;
  chunk_count: number;
  token_count: number;
  task_id: number | null;
}

export interface IngestQueued {
  document_id: number;
  task_id: number;
}
