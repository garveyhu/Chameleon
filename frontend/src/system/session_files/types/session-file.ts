export interface SessionFileItem {
  id: number;
  session_id: string;
  end_user_id: string | null;
  object_url: string;
  object_id: string;
  filename: string;
  mime: string;
  size: number;
  /** image / audio / document / data / other */
  kind: string;
  document_id: number | null;
  ephemeral_kb_id: number | null;
  /** uploaded / parsing / ready / failed */
  status: string;
  error: string | null;
  created_at: string;
}

export interface SessionFileDetail extends SessionFileItem {
  session_title: string | null;
  document_title: string | null;
  chunk_count: number | null;
}
