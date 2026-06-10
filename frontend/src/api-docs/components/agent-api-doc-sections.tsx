/** 应用 API 文档的共享 sections（单一来源）
 *
 * 编辑器「访问 API」tab（agent-api-doc-view）与独立路由页（agent-api-doc-page)
 * 此前各自手写一份相同的 sections——流式协议示例曾在两处同步漂移成错误协议
 * （审计 P0）。收口为一个构造函数，调用方只传差异化的密钥来源指引。
 *
 * 协议示例的正确性由后端 tests/test_api_docs_contract.py 对照 OpenAPI 锁定。
 */
import type { ReactNode } from 'react';

import type { ApiDocSection } from '@/api-docs/components/api-doc-template';

export const buildAgentApiDocSections = (
  base: string,
  agentKey: string,
  keySourceHint: ReactNode,
): ApiDocSection[] => [
  {
    id: 'auth',
    label: '鉴权',
    desc: (
      <>
        Service API 用 API-Key 鉴权，强烈建议存放在后端、勿泄露到客户端。每个请求都在{' '}
        <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
          Authorization
        </code>{' '}
        头携带。密钥为本应用的 <strong>app-</strong> 作用域密钥（{keySourceHint}），key
        已绑定到 <code className="font-mono text-[11.5px]">{agentKey}</code>
        ，路径无须再带应用标识。
      </>
    ),
    code: 'Authorization: Bearer app-xxxxxxxxxxxxxxxx',
  },
  {
    id: 'info',
    label: '应用信息',
    method: 'GET',
    path: '/info',
    desc: '返当前 key 绑定的应用信息（名称、provider、版本等）—— 用于客户端启动时确认 key 代表什么应用。',
    code: `curl '${base}/info' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'invoke',
    label: '调用应用',
    method: 'POST',
    path: '/invoke',
    desc: '统一调用端点。app 作用域 key 自动锁定到绑定的应用；body.stream=true 走 SSE。',
    code: `curl -X POST '${base}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "input": "你好",\n    "user": "end-user-id-12345",\n    "session_id": null,\n    "stream": false\n  }'`,
  },
  {
    id: 'stream',
    label: '流式调用 (SSE)',
    method: 'POST',
    path: '/invoke',
    desc: '同一端点，body 传 stream:true 即走 SSE 具名事件流（event: 类型 + data: JSON）。事件：delta(增量文本) / step(运行步骤，含 HITL 暂停) / citation / tool_call / tool_result / metadata / done(终态，data=完整结果) / error。以 done 或 error 收尾（无 [DONE] 标记），每 15s 一行 ": ping" 注释保活。用 fetch+ReadableStream 解析——EventSource 不支持 POST。',
    code: `curl -N -X POST '${base}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "input": "你好", "stream": true, "user": "end-user-id" }'\n\n# 响应（text/event-stream，具名事件）\nevent: delta\ndata: {"text": "你"}\n\nevent: delta\ndata: {"text": "好"}\n\nevent: done\ndata: {"session_id": "sess_...", "request_id": "req_...", "answer": "你好", "usage": {"total_tokens": 40}}`,
  },
  {
    id: 'sessions',
    label: '会话列表',
    method: 'GET',
    path: '/sessions',
    desc: '列当前 key 范围内的历史会话；?user= 按终端用户过滤；?page= / ?page_size= 分页。',
    code: `curl '${base}/sessions?user=end-user-id-12345&page=1&page_size=10' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'messages',
    label: '会话消息',
    method: 'GET',
    path: '/sessions/{session_id}/messages',
    desc: '加载某历史会话的消息列表（按 seq 正序）。',
    code: `curl '${base}/sessions/sess_xxx/messages' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'openai',
    label: 'OpenAI 兼容',
    method: 'POST',
    path: '/chat/completions',
    desc: '标准 OpenAI 协议子集，model 传 agent_key。content 仅支持纯字符串（图理解走 /invoke 的 attachments）；temperature 等采样参数会被忽略。',
    code: `curl -X POST '${base}/chat/completions' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "model": "${agentKey}",\n    "messages": [\n      {"role": "user", "content": "你好"}\n    ],\n    "user": "end-user-id-12345",\n    "stream": false\n  }'`,
  },
  {
    id: 'files',
    label: '文件上传',
    method: 'POST',
    path: '/files/presigned-upload',
    desc: '多模态场景：先取预签名地址直传文件（filename / content_type / size 均必填），finalize 后在调用的 attachments 里引用。',
    code: `curl -X POST '${base}/files/presigned-upload' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "filename": "doc.pdf", "content_type": "application/pdf", "size": 102400 }'`,
  },
];
