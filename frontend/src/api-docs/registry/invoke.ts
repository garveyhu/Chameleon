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
        name: 'attachments',
        type: 'Attachment[] | null',
        required: false,
        default: null,
        desc: '本次调用附带的文件。图片 / 音频走多模态进 LLM；文档 / 数据类（PDF、Word、表格等）自动入会话级临时知识库（ephemeral RAG），命中片段注入上下文并产出 citation。先用 /v1/files/presigned-upload 三步拿到 object_url 再传入。每条 Attachment：{ object_url, filename?, mime, size? }',
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
        desc: 'provider-specific 运行时覆盖，随应用来源而异。生成类应用（生图/视频）：options.gen_params（尺寸 / 分辨率 / 时长 / 数量等，见「生成应用」一节）、options.input_images（图生视频首帧图 url 数组）。外部编排应用：Dify 透传为 inputs、FastGPT 为 variables。平台原生（代码 / 工作流）应用当前不消费通用采样参数（temperature 等），模型参数在应用配置中管理。',
      },
      {
        name: 'resume_answer',
        type: 'string | null',
        required: false,
        default: null,
        desc: 'durable HITL 续跑：上次调用因应用 ask_human 暂停（流中 step 事件 name=human_input_pending / 非流式 done.steps 含同名记录）后，带人工回答续跑。必须同时传暂停时的 session_id；input 传该回答的展示文本（落会话历史）。续跑从暂停点恢复，已完成的副作用不会重复执行。',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - application/json (stream=false)',
        desc: '非流式：返回完整 InvokeResponse',
        example: {
          code: 200,
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
        desc: 'SSE 为具名事件流：每个事件两行 event: <类型> + data: {JSON}。事件类型：delta(增量文本 {"text"}) / step(运行步骤；HITL 暂停时 name=human_input_pending、status=paused，带 prompt/run_id) / citation(知识库引用) / tool_call / tool_result / metadata(usage 或媒体产物) / done(终态，data=完整 InvokeResult) / error({"message","code"?})。以 done 或 error 事件收尾，没有 [DONE] 标记；每 15s 发一行 ": ping" 注释保活（按 SSE 规范忽略）。注意：EventSource 不支持 POST，请用 fetch + ReadableStream 解析。',
        example:
          'event: delta\ndata: {"text": "你"}\n\nevent: delta\ndata: {"text": "好"}\n\nevent: done\ndata: {"session_id": "sess_01H...", "request_id": "req_01H...", "answer": "你好", "steps": [], "citations": [], "tool_calls": [], "usage": {"prompt_tokens": 12, "completion_tokens": 28, "total_tokens": 40}}',
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
    id: 'invoke-generation',
    group: 'invoke',
    order: 15,
    title: '生成应用：生图 / 视频',
    method: 'POST',
    path: '/v1/invoke',
    auth: 'bearer-key',
    desc: '生成类应用（绑定图片 / 视频模型）走同一 /v1/invoke 端点：input 为生成提示词，options.gen_params 调生成参数，options.input_images 传图生视频首帧。产物落对象存储，answer 字段以 Markdown 形式回传（图片 ![](url)、视频 [▶视频](url)）。按张 / 按秒计费（人民币元，见可观测）。',
    bodyParams: [
      {
        name: 'input',
        type: 'string',
        required: true,
        desc: '生成提示词（prompt）',
        example: 'a red sports car on a mountain road',
      },
      {
        name: 'options.gen_params',
        type: 'object',
        required: false,
        default: '{}',
        desc: '生成参数（随应用绑定的模型而异，以应用配置页展示的参数面板为准）。图片常用：size("1024*1024") / n(张数) / negative_prompt / seed；视频常用：resolution("720P"|"1080P") / duration(秒) / seed。',
      },
      {
        name: 'options.input_images',
        type: 'string[]',
        required: false,
        default: '[]',
        desc: '图生视频（i2v）首帧图 url（仅视频模型用）。本地图会自动转 base64 内联，外部图直接透传。',
      },
      {
        name: 'user',
        type: 'string | null',
        required: false,
        default: null,
        desc: '终端用户外部标识（会话归属 / 计费统计）',
      },
    ],
    responses: [
      {
        code: 200,
        name: '200 - 生图（application/json）',
        desc: 'answer 为 Markdown 图片，url 为对象存储签名地址',
        example: {
          code: 200,
          message: 'ok',
          data: {
            session_id: 'sess_01H...',
            request_id: 'req_01H...',
            answer: '![image](https://oss.example.com/mediagen/.../out.png?sig=...)',
            usage: null,
          },
        },
      },
    ],
    cURL: `# 生图（绑定 qwen-image-2.0 等图片模型的应用）
curl -X POST '{BASE}/v1/invoke' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "input": "a red sports car on a mountain road",
    "options": { "gen_params": { "size": "1024*1024", "n": 1 } }
  }'

# 图生视频（绑定 wan2.7-i2v 等视频模型的应用）
curl -X POST '{BASE}/v1/invoke' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "input": "镜头缓慢推进，云雾流动",
    "options": {
      "gen_params": { "resolution": "720P", "duration": 5 },
      "input_images": ["https://your-cdn.com/first-frame.png"]
    }
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
          code: 200,
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
