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
    desc: '标准 OpenAI Chat Completions 协议子集。model 字段当 agent_key 使用，可直接接入 OpenAI 官方 SDK / LangChain / 第三方工具。stream=true 走 SSE chunk + [DONE]。兼容范围（诚实声明）：支持 model / messages / stream / session_id / user；temperature、top_p、max_tokens、tools、tool_choice、response_format、n、stop、stream_options 会被接受但静默忽略（模型参数在应用配置中管理）；无 GET /v1/models 端点（SDK 的模型发现不可用，直接填 agent_key）；非 2xx 错误返回平台统一 Result 包装（{code, message, success}）而非 OpenAI error 对象，流中错误为 {"error": {message, type, code}} chunk + [DONE]。',
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
        desc: '消息数组，每条 { role, content }。role ∈ user / assistant / system / developer / tool（developer 按 OpenAI 新版语义映射为 system）。content 仅支持纯字符串——OpenAI 视觉格式的内容块数组暂不支持；图理解请改用 POST /v1/invoke 的 attachments 字段（图片走多模态进 LLM）。最后一条消息必须是 user。',
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
          'data: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\ndata: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}\ndata: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}\ndata: {"id":"chatcmpl-xx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\ndata: [DONE]',
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
  }'

# 图理解请用 POST /v1/invoke + attachments（本端点 content 仅支持字符串）`,
  },
];

export default ENDPOINTS;
