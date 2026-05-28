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
  /** 解析后文本字符数（用于看是小文件全文还是大文件切块） */
  text_size: number | null;
  /** true=小文件全文喂 prompt；false=大文件已切块 */
  use_full_text: boolean;
  /** uploaded / parsing / indexing / ready / failed */
  status: string;
  error: string | null;
  created_at: string;
}

export interface SessionFileDetail extends SessionFileItem {
  session_title: string | null;
  chunk_count: number;
}

/** GET /v1/admin/session-files/{id}/preview 返回 */
export interface SessionFilePreview {
  kind: 'text' | 'image' | 'pdf' | 'office' | 'audio' | 'download_only';
  mime: string;
  filename: string;
  size: number;
  /** text / office 时填 */
  text: string | null;
  /** image / pdf / audio / download_only 时填 presigned GET URL */
  url: string | null;
  truncated: boolean;
  /** 异常 / 提示信息 */
  note: string | null;
}
