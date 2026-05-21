export interface KbItem {
  id: number;
  kb_key: string;
  name: string;
  description: string | null;
  embedding_model: string;
  embedding_dim: number;
  chunk_size: number;
  chunk_overlap: number;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChunkItem {
  id: number;
  document_id: number;
  chunk_index: number;
  content: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}
