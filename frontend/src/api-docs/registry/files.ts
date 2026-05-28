/** 文件上传端点（/v1/files/*）
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/files/api.py + schemas.py
 * 多模态场景：先取 presigned PUT URL 直传 MinIO → finalize 通知后端 → 拿 object_url
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'files.presigned-upload',
    group: 'files',
    order: 10,
    title: '取预签名上传地址',
    method: 'POST',
    path: '/v1/files/presigned-upload',
    auth: 'bearer-key',
    desc: '生成直传 MinIO 的 presigned PUT URL。拿到 upload_url 后客户端直接 PUT 文件二进制（不带额外 header）。允许 mime：image/png|jpeg|webp|gif、audio/mp3|wav|ogg|webm、application/pdf。最大 20MB。',
    bodyParams: [
      { name: 'filename', type: 'string', required: true, desc: '原始文件名（1-256 字符）', example: 'doc.pdf' },
      { name: 'content_type', type: 'string', required: true, desc: 'MIME 类型，必须在白名单内', example: 'application/pdf' },
      { name: 'size', type: 'integer', required: true, desc: '声明大小（字节），1 ≤ size ≤ 20MB' },
      {
        name: 'namespace',
        type: 'string',
        required: false,
        default: 'multimodal',
        desc: '业务方分组前缀（如 multimodal/chat、kb/upload）',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            object_id: 'multimodal/abc123xyz.pdf',
            upload_url: 'https://minio.example.com/...presigned-put-url...',
            object_url: 'https://minio.example.com/...presigned-get-url...',
            expires_in: 86400,
            max_bytes: 20971520,
          },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/files/presigned-upload' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "filename": "doc.pdf",
    "content_type": "application/pdf",
    "size": 524288
  }'`,
  },
  {
    id: 'files.finalize',
    group: 'files',
    order: 20,
    title: '通知上传完成',
    method: 'POST',
    path: '/v1/files/{object_id}/finalize',
    auth: 'bearer-key',
    desc: '客户端 PUT 上传完成后调用，后端 stat MinIO 确认存在 + size 合法，返长效 presigned GET URL 供 ContentBlock 引用。',
    pathParams: [
      {
        name: 'object_id',
        type: 'string',
        required: true,
        desc: 'presigned-upload 返回的 object_id（含 namespace 前缀，用 path 风格）',
      },
    ],
    bodyParams: [
      {
        name: 'expected_size',
        type: 'integer | null',
        required: false,
        desc: '客户端声称的大小，后端会与实际 stat 对比；不一致直接拒绝',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            object_id: 'multimodal/abc123xyz.pdf',
            size: 524288,
            content_type: 'application/pdf',
            etag: '"xxxxxxxx"',
            object_url: 'https://minio.example.com/...long-presigned-get...',
          },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/files/multimodal/abc123xyz.pdf/finalize' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "expected_size": 524288 }'`,
  },
];

export default ENDPOINTS;
