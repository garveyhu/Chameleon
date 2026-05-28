/** 嵌入式端点（/v1/embed/{embed_key}/*）
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/embed/api.py + schemas.py
 * 鉴权：origin 白名单 + 颁发 session_token（短期）
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'embed.config',
    group: 'embed',
    order: 10,
    title: '取公开配置',
    method: 'GET',
    path: '/v1/embed/{embed_key}/config',
    auth: 'origin-whitelist',
    desc: '业务方 widget 首次加载时拉公开配置（ui_config + behavior）。仅按 Origin 白名单校验，无 token。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用的公开 key' }],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            embed_key: 'em_xxx',
            name: '产品助手',
            description: '产品官网右下角助手',
            ui_config: { theme: 'light', primary_color: '#2563eb' },
            behavior: { show_citations: true },
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/embed/em_xxx/config' \\
  -H 'Origin: https://your-site.example.com'`,
  },
  {
    id: 'embed.session.create',
    group: 'embed',
    order: 20,
    title: '颁发 session token',
    method: 'POST',
    path: '/v1/embed/{embed_key}/session',
    auth: 'origin-whitelist',
    desc: '用户打开 widget 时颁短期 session_token。按 embed.session_policy.identification_mode 三选一传 device_id / external_user_id / jwt_token。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      {
        name: 'device_id',
        type: 'string',
        required: false,
        desc: 'mode=anonymous_device 时传（前端持久化 uuid，8-128 字符）',
      },
      {
        name: 'external_user_id',
        type: 'string',
        required: false,
        desc: 'mode=external_user_id 时传（接入方系统的用户 id，1-128 字符）',
      },
      {
        name: 'jwt_token',
        type: 'string',
        required: false,
        desc: 'mode=signed_jwt 时传（HS256 签名，sub claim 当 end_user_id）',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: { session_token: 'eyJhbGciOi...', expires_in: 3600 },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/session' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "device_id": "browser-uuid-1234..." }'`,
  },
  {
    id: 'embed.invoke',
    group: 'embed',
    order: 30,
    title: '调用（非流式）',
    method: 'POST',
    path: '/v1/embed/{embed_key}/invoke',
    auth: 'session-token',
    desc: 'widget 发送一条用户输入，返回完整响应。session_token 已绑 end_user_id，自动关联会话归属。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: '颁发接口返回的短期 token' },
      { name: 'input', type: 'string', required: true, desc: '用户输入（1-8000 字符）' },
      {
        name: 'attachments',
        type: 'Attachment[]',
        required: false,
        desc: '附件（Phase A 仅图/音走多模态进 LLM；先用 /v1/files/presigned-upload 拿 object_url）',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: { answer: '需要我帮你做什么？', session_id: 'sess_01H...', request_id: 'req_01H...' },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/invoke' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "session_token": "{TOKEN}",
    "input": "你好"
  }'`,
  },
  {
    id: 'embed.invoke.stream',
    group: 'embed',
    order: 40,
    title: '调用（SSE 流式）',
    method: 'POST',
    path: '/v1/embed/{embed_key}/invoke/stream',
    auth: 'session-token',
    desc: '同 invoke 入参，响应为 SSE。chunk 协议同 /v1/invoke 流式。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'input', type: 'string', required: true, desc: '用户输入' },
      {
        name: 'attachments',
        type: 'Attachment[]',
        required: false,
        desc: '同非流式：Phase A 图/音走多模态',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - text/event-stream',
        example:
          'data: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好"}\ndata: [DONE]',
      },
    ],
    cURL: `curl -N -X POST '{BASE}/v1/embed/em_xxx/invoke/stream' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "session_token": "{TOKEN}",
    "input": "你好"
  }'`,
  },
  {
    id: 'embed.sessions.list',
    group: 'embed',
    order: 50,
    title: '我的会话列表',
    method: 'GET',
    path: '/v1/embed/{embed_key}/sessions',
    auth: 'session-token',
    desc: '按 session_token 解出的终端用户，列其所有历史会话（按活跃时间倒序）。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    queryParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token（GET 不能用 body）' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: [
            {
              session_id: 'sess_01H...',
              title: '产品咨询',
              last_message_at: '2026-05-28T03:21:00Z',
              created_at: '2026-05-28T03:20:00Z',
            },
          ],
        },
      },
    ],
    cURL: `curl '{BASE}/v1/embed/em_xxx/sessions?session_token={TOKEN}' \\
  -H 'Origin: https://your-site.example.com'`,
  },
  {
    id: 'embed.sessions.messages',
    group: 'embed',
    order: 60,
    title: '我的会话消息',
    method: 'GET',
    path: '/v1/embed/{embed_key}/sessions/{session_id}/messages',
    auth: 'session-token',
    desc: '加载某历史会话的消息（按 seq 正序，硬上限 500 条）。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
    ],
    queryParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [{ code: 200, desc: '返回 MessageItem[]' }],
    cURL: `curl '{BASE}/v1/embed/em_xxx/sessions/sess_01H.../messages?session_token={TOKEN}' \\
  -H 'Origin: https://your-site.example.com'`,
  },
  {
    id: 'embed.sessions.new',
    group: 'embed',
    order: 70,
    title: '开新会话',
    method: 'POST',
    path: '/v1/embed/{embed_key}/sessions/new',
    auth: 'session-token',
    desc: '同 token 直接 rebind 一个新 session_id（不需要刷新页面）。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: { session_token: 'eyJ...', session_id: 'sess_new_01H...', expires_in: 3600 },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/sessions/new' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}" }'`,
  },
  {
    id: 'embed.sessions.delete',
    group: 'embed',
    order: 80,
    title: '删除我的会话',
    method: 'POST',
    path: '/v1/embed/{embed_key}/sessions/{session_id}/delete',
    auth: 'session-token',
    desc: 'end-user 软删自己的会话；受 session_policy.allow_user_manage 限制。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
    ],
    bodyParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [{ code: 200, desc: '{ deleted: true }' }],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/sessions/sess_01H.../delete' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}" }'`,
  },
  {
    id: 'embed.sessions.rename',
    group: 'embed',
    order: 90,
    title: '重命名我的会话',
    method: 'POST',
    path: '/v1/embed/{embed_key}/sessions/{session_id}/name',
    auth: 'session-token',
    desc: 'end-user 重命名会话；受 session_policy.allow_user_manage 限制。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
    ],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'title', type: 'string', required: true, desc: '新标题（1-255 字符）' },
    ],
    responses: [{ code: 200, desc: '返回更新后的 EmbedSessionItem' }],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/sessions/sess_01H.../name' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}", "title": "重要咨询" }'`,
  },
  {
    id: 'embed.feedback',
    group: 'embed',
    order: 100,
    title: '反馈打分',
    method: 'POST',
    path: '/v1/embed/{embed_key}/feedback',
    auth: 'origin-whitelist',
    desc: '业务方 widget 反馈入口（👍 / 👎 / 评分 / 评语），写入 scores 表，source 固定 "feedback"。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_id', type: 'string', required: false, desc: '会话 ID（可选）' },
      { name: 'message_id', type: 'integer', required: false, desc: '消息 ID（可选）' },
      { name: 'value', type: 'enum: up | down | star', required: true, desc: '反馈类型' },
      { name: 'score', type: 'number', required: false, desc: 'star 时的评分值' },
      { name: 'comment', type: 'string', required: false, desc: '评语' },
    ],
    responses: [{ code: 200, desc: '返回写入的 ScoreItem' }],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/feedback' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "session_id": "sess_01H...",
    "message_id": 2,
    "value": "up"
  }'`,
  },
];

export default ENDPOINTS;
