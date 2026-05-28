/** OpenAI 兼容端点（/v1/chat/completions）
 *
 * 后端真相源：backend/chameleon-api/src/chameleon/api/openai/api.py + schemas.py
 * model 字段当 agent_key 使用（与 FastGPT 一致）
 */
import type { EndpointSpec } from '@/api-docs/types/endpoint';

const ENDPOINTS: EndpointSpec[] = [
  {
    id: 'openai.chat',
    group: 'openai',
    order: 10,
    title: 'Chat Completions',
    method: 'POST',
    path: '/v1/chat/completions',
    auth: 'bearer-key',
    desc: '标准 OpenAI Chat Completions 协议子集。model 字段当 agent_key 使用，可直接接入 OpenAI 官方 SDK / LangChain / 第三方工具。stream=true 走 SSE chunk + [DONE]。',
    bodyParams: [
      {
        name: 'model',
        type: 'string',
        required: true,
        desc: '应用标识（agent_key）。OpenAI 客户端的 model 字段在这里复用为应用身份。',
        example: 'agt_my_app',
      },
      {
        name: 'messages',
        type: 'OAMessage[]',
        required: true,
        desc: '消息数组，每条 { role, content }。role ∈ user / assistant / system / tool。',
      },
      {
        name: 'stream',
        type: 'boolean',
        required: false,
        default: false,
        desc: 'true → SSE chunk + [DONE]；false → 单次 chat.completion 响应',
      },
      {
        name: 'session_id',
        type: 'string | null',
        required: false,
        default: null,
        desc: '多轮会话（可选，缺省每次新建，无状态）',
      },
      {
        name: 'user',
        type: 'string | null',
        required: false,
        default: null,
        desc: 'OpenAI 协议原生字段：终端用户外部标识，用于会话归属、按用户统计计费',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - application/json (stream=false)',
        example: {
          id: 'chatcmpl-xxxx',
          object: 'chat.completion',
          created: 1717000000,
          model: 'agt_my_app',
          choices: [
            {
              index: 0,
              message: { role: 'assistant', content: '你好！需要我帮你做什么？' },
              finish_reason: 'stop',
            },
          ],
          usage: { prompt_tokens: 12, completion_tokens: 28, total_tokens: 40 },
        },
      },
      {
        code: 200,
        name: '200 - text/event-stream (stream=true)',
        example:
          'data: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}\ndata: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}\ndata: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\ndata: [DONE]',
      },
    ],
    cURL: `curl -X POST '{BASE}/v1/chat/completions' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "agt_my_app",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "user": "end-user-id-12345",
    "stream": false
  }'`,
  },
];

export default ENDPOINTS;
