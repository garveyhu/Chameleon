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
          code: 200,
          message: 'ok',
          data: {
            embed_key: 'em_xxx',
            name: '产品助手',
            description: '产品官网右下角助手',
            ui_config: { theme: 'light', primary_color: '#2563eb' },
            behavior: { show_citations: true },
            session_policy: { identification_mode: 'anonymous_device', allow_user_manage: true },
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
          code: 200,
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
        name: 'session_id',
        type: 'string | null',
        required: false,
        desc: 'widget 当前显示的会话 id（权威）。传了就落到该会话；缺省回退 token 绑定的会话',
      },
      {
        name: 'attachments',
        type: 'Attachment[]',
        required: false,
        desc: '附件（图/音走多模态进 LLM，文档/数据走会话临时 RAG）。先用本组的 POST /v1/embed/{embed_key}/files/presigned-upload 三步上传拿 object_url——不要用 bearer-key 鉴权的 /v1/files 系列，widget 手里只有 session_token',
      },
      {
        name: 'resume_answer',
        type: 'string | null',
        required: false,
        desc: 'durable HITL 续跑：流式调用收到 pending 后，带人工回答重调本端点（流式端点同理）续跑暂停的 run',
      },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 200,
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
    desc: '同 invoke 入参（含 session_id / attachments / resume_answer），响应为 SSE。注意：协议与 /v1/invoke 的具名事件流不同——本端点是匿名 data 行，按顶层 key 判型：meta(首条，会话/请求 id) / delta(增量文本字符串) / citation(引用) / pending(HITL 暂停 {prompt, call_index, run_id}，回填后带 resume_answer 重调本端点续跑) / error({type, message, code?}) / end({end: true, answer, usage})。末尾 data: [DONE] 终止标记。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'input', type: 'string', required: true, desc: '用户输入' },
      { name: 'session_id', type: 'string | null', required: false, desc: '同非流式' },
      {
        name: 'attachments',
        type: 'Attachment[]',
        required: false,
        desc: '同非流式：经 embed 专用上传端点拿 object_url',
      },
      {
        name: 'resume_answer',
        type: 'string | null',
        required: false,
        desc: 'HITL 续跑人工回答（对应上次流中的 pending）',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - text/event-stream',
        example:
          'data: {"meta": {"agent": "agt_x", "session_id": "sess_01H...", "request_id": "req_01H..."}}\ndata: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好", "usage": {"input_tokens": 12, "output_tokens": 28}}\ndata: [DONE]',
      },
      {
        code: 200,
        name: '200 - HITL 暂停（durable 应用）',
        desc: '应用 ask_human 暂停时收到 pending 后流结束；widget 渲染回填框，用户回答后带 resume_answer 重调本端点续跑',
        example:
          'data: {"meta": {...}}\ndata: {"pending": {"prompt": "金额超阈值，是否批准？", "call_index": 0, "run_id": "run_01H..."}}\ndata: [DONE]',
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
          code: 200,
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
    desc: '加载某历史会话的消息（按 seq 正序，硬上限 500 条）。注意副作用：调用会把 session_token 重新绑定到该会话（后续不带 session_id 的 invoke 落到这里）。',
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
          code: 200,
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
    id: 'embed.files.presign',
    group: 'embed',
    order: 92,
    title: '附件上传：取预签名 URL',
    method: 'POST',
    path: '/v1/embed/{embed_key}/files/presigned-upload',
    auth: 'session-token',
    desc: 'widget 附件上传三步第 1 步：按 behavior 配置校验大小/类型后返回预签名直传 URL。第 2 步用 PUT 把文件字节直传 upload_url（不经平台）。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'filename', type: 'string', required: true, desc: '原文件名' },
      { name: 'content_type', type: 'string', required: true, desc: 'MIME 类型' },
      { name: 'size', type: 'integer', required: true, desc: '文件字节数（受 behavior 上限约束）' },
    ],
    responses: [
      {
        code: 200,
        example: {
          code: 200,
          message: 'ok',
          data: { upload_url: 'https://minio.../presigned...', object_id: 'embed-attach/em_xxx/uuid/photo.png' },
        },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/files/presigned-upload' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}", "filename": "photo.png", "content_type": "image/png", "size": 102400 }'`,
  },
  {
    id: 'embed.files.finalize',
    group: 'embed',
    order: 93,
    title: '附件上传：登记完成',
    method: 'POST',
    path: '/v1/embed/{embed_key}/files/{object_id}/finalize',
    auth: 'session-token',
    desc: '三步第 3 步：直传完成后登记，返回长效 object_url（之后作为 invoke 的 attachments[].object_url 传入）。文档/数据类会触发异步解析入会话临时知识库。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'object_id', type: 'string', required: true, desc: '第 1 步返回的 object_id（URL encode 后拼进路径）' },
    ],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'filename', type: 'string', required: false, desc: '原文件名（落库展示用）' },
    ],
    responses: [{ code: 200, desc: '返回 { object_url, file_id, ... }' }],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/files/embed-attach%2Fem_xxx%2Fuuid%2Fphoto.png/finalize' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}", "filename": "photo.png" }'`,
  },
  {
    id: 'embed.files.status',
    group: 'embed',
    order: 94,
    title: '附件解析状态',
    method: 'POST',
    path: '/v1/embed/{embed_key}/files/{file_id}/status',
    auth: 'session-token',
    desc: '轮询文档类附件的解析进度：uploaded → parsing → indexing → ready / failed。ready 后该文件内容可被会话内提问命中（临时 RAG）。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'file_id', type: 'integer', required: true, desc: 'finalize 返回的 file_id' },
    ],
    bodyParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [
      { code: 200, example: { code: 200, message: 'ok', data: { id: 12, status: 'ready', error: null } } },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/files/12/status' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}" }'`,
  },
  {
    id: 'embed.files.list',
    group: 'embed',
    order: 95,
    title: '我的会话附件列表',
    method: 'GET',
    path: '/v1/embed/{embed_key}/sessions/{session_id}/files',
    auth: 'session-token',
    desc: 'end-user 拉自己在此会话上传过的附件（按 end_user 隔离）。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
    ],
    queryParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [{ code: 200, desc: '返回 [{ id, filename, mime, size, kind, status, object_url, created_at }]' }],
    cURL: `curl '{BASE}/v1/embed/em_xxx/sessions/sess_01H.../files?session_token={TOKEN}' \\
  -H 'Origin: https://your-site.example.com'`,
  },
  {
    id: 'embed.files.delete',
    group: 'embed',
    order: 96,
    title: '删除我的会话附件',
    method: 'POST',
    path: '/v1/embed/{embed_key}/sessions/{session_id}/files/{file_id}/delete',
    auth: 'session-token',
    desc: '删除附件及其临时索引（后续提问不再命中该文件内容）。',
    pathParams: [
      { name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' },
      { name: 'session_id', type: 'string', required: true, desc: '会话 ID' },
      { name: 'file_id', type: 'integer', required: true, desc: '附件 ID' },
    ],
    bodyParams: [{ name: 'session_token', type: 'string', required: true, desc: 'session_token' }],
    responses: [{ code: 200, desc: '{ deleted: true }' }],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/sessions/sess_01H.../files/12/delete' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}" }'`,
  },
  {
    id: 'embed.followups',
    group: 'embed',
    order: 98,
    title: '建议追问',
    method: 'POST',
    path: '/v1/embed/{embed_key}/suggest-followups',
    auth: 'session-token',
    desc: '基于刚才的问答生成 3 个建议追问。widget 在流式 end 后调用，按 behavior.show_followups 配置渲染气泡。',
    pathParams: [{ name: 'embed_key', type: 'string', required: true, desc: '嵌入应用 key' }],
    bodyParams: [
      { name: 'session_token', type: 'string', required: true, desc: 'session_token' },
      { name: 'question', type: 'string', required: true, desc: '刚才的用户问题' },
      { name: 'answer', type: 'string', required: true, desc: '刚才的应用回答' },
    ],
    responses: [
      {
        code: 200,
        example: { code: 200, message: 'ok', data: ['它支持哪些模型？', '怎么计费？', '可以私有化部署吗？'] },
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/embed/em_xxx/suggest-followups' \\
  -H 'Origin: https://your-site.example.com' \\
  -H 'Content-Type: application/json' \\
  -d '{ "session_token": "{TOKEN}", "question": "你们是做什么的", "answer": "我们是..." }'`,
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
