/** 知识库端点（/v1/kb/*）
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/knowledge/api.py + schemas.py
 * 鉴权：kbs- 作用域 key（path 不带 kb_key 占位）或 global key 显式 query.kb_key
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'kb.info',
    group: 'kb',
    order: 10,
    title: '知识库信息',
    method: 'GET',
    path: '/v1/kb',
    auth: 'bearer-key',
    desc: '返当前 key 绑定的 KB 元信息（kb_key / name / description / embedding_model / chunk_size 等）。kbs- 作用域 key 路径自带身份；global key 需在 query 显式传 kb_key。',
    queryParams: [
      { name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要；kb 作用域 key 忽略' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            id: 1,
            kb_key: 'kb_faq',
            name: '产品 FAQ',
            description: '客服常见问题',
            embedding_model: 'text-embedding-3-large',
            embedding_dim: 3072,
            chunk_size: 800,
            chunk_overlap: 100,
            chunk_strategy: { mode: 'paragraph' },
            created_at: '2026-05-01T10:00:00Z',
            updated_at: '2026-05-20T12:00:00Z',
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/kb' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'kb.update',
    group: 'kb',
    order: 20,
    title: '更新知识库',
    method: 'POST',
    path: '/v1/kb/update',
    auth: 'bearer-key',
    desc: '改 KB 名称 / 描述 / 切块参数（不会触发已有文档重分块）。',
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    bodyParams: [
      { name: 'name', type: 'string', required: false, desc: 'KB 名称（可选）' },
      { name: 'description', type: 'string', required: false, desc: 'KB 描述' },
      { name: 'chunk_size', type: 'integer', required: false, desc: '默认切块长度（10 ≤ x ≤ 4000）' },
      { name: 'chunk_overlap', type: 'integer', required: false, desc: '默认切块重叠（0 ≤ x ≤ 500）' },
      { name: 'chunk_strategy', type: 'object', required: false, desc: '默认切块策略，如 { mode: "token", chunk_size: 512 }' },
    ],
    responses: [{ code: 200, desc: '返回更新后的 KbItem' }],
    cURL: `curl -X POST '{BASE}/v1/kb/update' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "description": "更新后的描述" }'`,
  },
  {
    id: 'kb.delete',
    group: 'kb',
    order: 30,
    title: '删除知识库',
    method: 'POST',
    path: '/v1/kb/delete',
    auth: 'bearer-key',
    desc: '软删整个知识库（含文档与切块）。',
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    responses: [{ code: 200, desc: '返回被删除的 KbItem' }],
    cURL: `curl -X POST '{BASE}/v1/kb/delete' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'kb.search',
    group: 'kb',
    order: 40,
    title: '检索',
    method: 'POST',
    path: '/v1/kb/search',
    auth: 'bearer-key',
    desc: '按 query 检索知识库，返回命中的切块（含相似度分项）。',
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    bodyParams: [
      { name: 'query', type: 'string', required: true, desc: '检索文本', example: '如何重置密码' },
      { name: 'top_k', type: 'integer', required: false, default: 5, desc: '返回条数，1 ≤ x ≤ 50' },
      { name: 'min_score', type: 'number', required: false, default: 0, desc: '最低分阈值，-1 ≤ x ≤ 1' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: [
            {
              id: 101,
              doc_id: 12,
              seq: 3,
              content: '若需重置密码，请前往设置 → 账户安全 → 重置密码。',
              score: 0.872,
              meta: { source: 'docs/account.md' },
            },
          ],
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/kb/search' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "query": "如何重置密码",
    "top_k": 5
  }'`,
  },
  {
    id: 'kb.docs.list',
    group: 'kb',
    order: 50,
    title: '文档列表',
    method: 'GET',
    path: '/v1/kb/documents',
    auth: 'bearer-key',
    desc: '分页列出知识库下的文档（含处理状态 status）。',
    queryParams: [
      { name: 'page', type: 'integer', required: false, default: 1, desc: '页码' },
      { name: 'page_size', type: 'integer', required: false, default: 20, desc: '每页条数，最大 200' },
      { name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            items: [
              {
                id: 1,
                kb_id: 1,
                title: '产品 FAQ',
                source_type: 'text',
                status: 'completed',
                created_at: '2026-05-20T10:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/kb/documents?page=1&page_size=20' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'kb.docs.create',
    group: 'kb',
    order: 60,
    title: '创建文档（异步入库）',
    method: 'POST',
    path: '/v1/kb/documents',
    auth: 'bearer-key',
    desc: '从 text 或 url 创建文档并异步切块 + 向量化。返回 task_id 供轮询状态。',
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    bodyParams: [
      { name: 'title', type: 'string', required: true, desc: '文档标题（1 ≤ len ≤ 255）' },
      { name: 'source_type', type: 'enum: text | url', required: false, default: 'text', desc: 'v1 仅支持 text / url' },
      { name: 'content', type: 'string', required: false, desc: 'source_type=text 时必填' },
      { name: 'source_uri', type: 'string', required: false, desc: 'source_type=url 时必填' },
      { name: 'mime_type', type: 'string', required: false, desc: 'MIME，缺省自动推断' },
      { name: 'meta', type: 'object', required: false, desc: '自定义元数据，会随切块写入' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: { task_id: 7, document_id: 12, status: 'queued' },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/kb/documents' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "title": "产品 FAQ",
    "source_type": "text",
    "content": "问：如何重置密码？\\n答：..."
  }'`,
  },
  {
    id: 'kb.docs.get',
    group: 'kb',
    order: 70,
    title: '文档详情',
    method: 'GET',
    path: '/v1/kb/documents/{doc_id}',
    auth: 'bearer-key',
    desc: '取单篇文档的元信息与处理状态。',
    pathParams: [{ name: 'doc_id', type: 'integer', required: true, desc: '文档 id' }],
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    responses: [{ code: 200, desc: '返回 DocumentItem' }],
    cURL: `curl '{BASE}/v1/kb/documents/12' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'kb.docs.update',
    group: 'kb',
    order: 80,
    title: '更新文档元数据',
    method: 'POST',
    path: '/v1/kb/documents/{doc_id}/update',
    auth: 'bearer-key',
    desc: '改文档 title / tags / meta（不触发重新分块）。',
    pathParams: [{ name: 'doc_id', type: 'integer', required: true, desc: '文档 id' }],
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    bodyParams: [
      { name: 'title', type: 'string', required: false, desc: '新标题' },
      { name: 'tags', type: 'string[]', required: false, desc: '标签数组' },
      { name: 'meta', type: 'object', required: false, desc: '元数据 patch' },
    ],
    responses: [{ code: 200, desc: '返回更新后的 DocumentItem' }],
    cURL: `curl -X POST '{BASE}/v1/kb/documents/12/update' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "meta": { "author": "张三" } }'`,
  },
  {
    id: 'kb.docs.delete',
    group: 'kb',
    order: 90,
    title: '删除文档',
    method: 'POST',
    path: '/v1/kb/documents/{doc_id}/delete',
    auth: 'bearer-key',
    desc: '软删文档并清除其切块与向量。',
    pathParams: [{ name: 'doc_id', type: 'integer', required: true, desc: '文档 id' }],
    queryParams: [{ name: 'kb_key', type: 'string', required: false, desc: '仅 global 作用域 key 需要' }],
    responses: [{ code: 200, desc: '返回被删除的 DocumentItem' }],
    cURL: `curl -X POST '{BASE}/v1/kb/documents/12/delete' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
];

export default ENDPOINTS;
