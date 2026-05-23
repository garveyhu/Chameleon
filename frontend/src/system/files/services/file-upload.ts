/** 多模态文件上传 helper —— P19.4 PR #42
 *
 * 三步流程：
 *  1. POST /v1/files/presigned-upload —— 拿 upload_url + object_url
 *  2. PUT upload_url（不带 Authorization；MinIO presigned 自验签）
 *  3. POST /v1/files/{object_id}/finalize —— stat 确认 + 拿长效 object_url
 *
 * 返回的 object_url 可直接放进 ImageUrlBlock / AudioUrlBlock。
 */

import { post } from '@/core/lib/request';
import type { EntityId } from '@/core/types/api';

export interface PresignedUploadResult {
  object_id: string;
  upload_url: string;
  object_url: string;
  expires_in: number;
  max_bytes: number;
}

export interface FinalizeResult {
  object_id: string;
  size: number;
  content_type: string | null;
  etag: string | null;
  object_url: string;
}

export interface UploadResult {
  object_id: string;
  object_url: string;
  size: number;
  content_type: string | null;
  mime_kind: 'image' | 'audio' | 'pdf' | 'other';
}

function classifyMime(t: string | null | undefined): UploadResult['mime_kind'] {
  if (!t) return 'other';
  if (t.startsWith('image/')) return 'image';
  if (t.startsWith('audio/')) return 'audio';
  if (t === 'application/pdf') return 'pdf';
  return 'other';
}

export async function uploadFile(
  file: File,
  opts: { namespace?: string } = {},
): Promise<UploadResult> {
  // 1. presigned
  const presign = await post<PresignedUploadResult>(
    '/v1/files/presigned-upload',
    {
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
      size: file.size,
      namespace: opts.namespace ?? 'multimodal',
    },
  );

  // 2. PUT 直传（不走 axios，免 Authorization 头干扰 presigned 签名）
  const putResp = await fetch(presign.upload_url, {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': file.type || 'application/octet-stream',
    },
  });
  if (!putResp.ok) {
    throw new Error(
      `MinIO upload 失败: ${putResp.status} ${putResp.statusText}`,
    );
  }

  // 3. finalize
  // path 里 object_id 含 '/'，axios 默认会 encode；让后端 :path 接受
  const finalUrl =
    `/v1/files/${encodeURIComponent(presign.object_id).replace(/%2F/g, '/')}/finalize`;
  const fin = await post<FinalizeResult>(finalUrl, {
    expected_size: file.size,
  });

  return {
    object_id: fin.object_id,
    object_url: fin.object_url,
    size: fin.size,
    content_type: fin.content_type,
    mime_kind: classifyMime(fin.content_type),
  };
}

/** 给 ContentBlock 列表用：把 UploadResult 转成对应 block dict */
export function toContentBlock(u: UploadResult): {
  type: 'image_url' | 'audio_url' | 'text';
  [k: string]: unknown;
} {
  if (u.mime_kind === 'image') {
    return {
      type: 'image_url',
      image_url: { url: u.object_url, detail: 'auto' },
    };
  }
  if (u.mime_kind === 'audio') {
    return {
      type: 'audio_url',
      audio_url: { url: u.object_url },
    };
  }
  // 其他类型暂以文本引用占位
  return {
    type: 'text',
    text: `[file:${u.object_url}]`,
  };
}

// 为类型一致性导出
export type EntityIdMaybe = EntityId | undefined;
