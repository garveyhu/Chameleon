/** 应用调用端点（/v1/invoke, /v1/info）—— 扁平 Dify 风契约
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/agent/api.py
 *   FlatInvokeRequest / AppInfoResponse / InvokeResponse
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'invoke',
    group: 'invoke',
    order: 10,
    title: '调用应用',
    method: 'POST',
    path: '/v1/invoke',
    auth: 'bearer-key',
    desc: '统一调用端点。app 作用域 key 自动锁定到绑定的应用；global 作用域 key 需在 body 显式带 agent_key。body.stream=true 则走 SSE 增量回包。',
    bodyParams: [
      {
        name: 'input',
        type: 'string | MessageInput[]',
        required: true,
        desc: 'string → 取 session 历史续接；MessageInput[] → 客户端自管历史（含 role / content / tool_call_id 等）',
        example: '你好',
      },
      {
        name: 'session_id',
        type: 'string | null',
        required: false,
        default: null,
        desc: '缺省 → 新建会话；传入续接（同 agent + 同 end_user 才行）',
      },
      {
        name: 'user',
        type: 'string | null',
        required: false,
        default: null,
        desc: '终端用户外部标识（接入方维护，对应 Dify / OpenAI 协议的 user）。用于会话归属、历史隔离、按用户统计计费。',
        example: 'end-user-id-12345',
      },
      {
        name: 'stream',
        type: 'boolean',
        required: false,
        default: false,
        desc: 'true → SSE 增量；false → 单次 JSON 全量响应',
      },
      {
        name: 'agent_key',
        type: 'string | null',
        required: false,
        default: null,
        desc: '仅 global 作用域 key 需要；app 作用域 key 不传或填 scope_ref 同值（路径已隐含应用身份）',
      },
      {
        name: 'context',
        type: 'object',
        required: false,
        default: '{}',
        desc: '业务上下文（user_id、tenant 等业务元数据，会被透传给 provider）',
      },
      {
        name: 'options',
        type: 'object',
        required: false,
        default: '{}',
        desc: 'provider-specific 运行时覆盖（temperature / top_p / max_tokens 等）',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - application/json (stream=false)',
        desc: '非流式：返回完整 InvokeResponse',
        example: {
          code: 0,
          message: 'ok',
          data: {
            session_id: 'sess_01H...',
            request_id: 'req_01H...',
            answer: '你好！需要我帮你做什么？',
            steps: [],
            citations: [],
            tool_calls: [],
            usage: { prompt_tokens: 12, completion_tokens: 28, total_tokens: 40 },
          },
        },
      },
      {
        code: 200,
        name: '200 - text/event-stream (stream=true)',
        desc: 'SSE：每行 data: {JSON}，末尾 data: [DONE]。delta 增量推送、end 携带最终 usage。',
        example:
          'data: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好", "usage": {"total_tokens": 40}}\ndata: [DONE]',
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/invoke' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "input": "你好",
    "user": "end-user-id-12345",
    "session_id": null,
    "stream": false
  }'`,
  },
  {
    id: 'info',
    group: 'invoke',
    order: 20,
    title: '应用信息',
    method: 'GET',
    path: '/v1/info',
    auth: 'bearer-key',
    desc: '返当前 key 绑定的应用信息（scope_type / 关联 agent 元信息 / key 自身的 name）。客户端启动时用于确认 key 代表哪个应用。',
    responses: [
      {
        code: 200,
        example: {
          code: 0,
          message: 'ok',
          data: {
            scope_type: 'app',
            agent: {
              key: 'agt_my_app',
              provider: 'graph',
              description: '客服助手 v2',
              version: '3',
              tags: ['support', 'production'],
            },
            name: '生产环境密钥',
          },
        },
      },
    ],
    cURL: `curl '{BASE}/v1/info' \\
  -H 'Authorization: Bearer {API_KEY}'`,
  },
];

export default ENDPOINTS;
