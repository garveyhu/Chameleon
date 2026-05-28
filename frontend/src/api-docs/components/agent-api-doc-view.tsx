/** 智能体 API 文档（编辑器「访问 API」tab 用）—— 套用通用 ApiDocTemplate
 *
 * Dify 风扁平契约：key 即应用身份，路径不再带 agent_key 占位。
 * `agent-` 作用域密钥已绑定到本应用，调用方只看 Bearer 头即可识别归属。
 */
import { useState } from 'react';

import { BookOpen, KeyRound } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/core/components/ui/button';
import {
  ApiDocTemplate,
  type ApiDocSection,
} from '@/api-docs/components/api-doc-template';
import { AgentKeysModal } from '@/system/graphs/components/app-shell/agent-keys-modal';
import type { GraphDetail } from '@/system/graphs/types/graph';

interface Props {
  graph: GraphDetail;
}

export const AgentApiDocView = ({ graph }: Props) => {
  const base = `${window.location.origin}/v1`;
  const key = graph.graph_key;
  const published = (graph.published_version ?? 0) > 0;
  const [keysOpen, setKeysOpen] = useState(false);

  const sections: ApiDocSection[] = [
    {
      id: 'auth',
      label: '鉴权',
      desc: (
        <>
          Service API 用 API-Key 鉴权，强烈建议存放在后端、勿泄露到客户端。每个请求都在{' '}
          <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
            Authorization
          </code>{' '}
          头携带。密钥为本应用的 <strong>app-</strong> 作用域密钥（右上角「管理密钥」生成），key
          本身已绑定到 <code className="font-mono text-[11.5px]">{key}</code>，路径无须再带应用标识。
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
      desc: '同一端点，body 传 stream:true 即走 SSE。每行 data: {JSON}，末尾 data: [DONE]。',
      code: `curl -N -X POST '${base}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "input": "你好", "stream": true, "user": "end-user-id" }'\n\n# 响应（text/event-stream）\ndata: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好", "usage": {...}}\ndata: [DONE]`,
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
      desc: '标准 OpenAI 协议，model 传 agent_key。可直接接入 OpenAI SDK / 第三方工具。',
      code: `curl -X POST '${base}/chat/completions' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "model": "${key}",\n    "messages": [\n      {"role": "user", "content": "你好"}\n    ],\n    "user": "end-user-id-12345",\n    "stream": false\n  }'`,
    },
    {
      id: 'files',
      label: '文件上传',
      method: 'POST',
      path: '/files/presigned-upload',
      desc: '多模态场景：先取预签名地址上传文件，再在调用里引用。',
      code: `curl -X POST '${base}/files/presigned-upload' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "filename": "doc.pdf", "content_type": "application/pdf" }'`,
    },
  ];

  return (
    <>
      <ApiDocTemplate
        title="访问 API"
        endpoint={base}
        sections={sections}
        status={
          published ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              服务运行中
            </span>
          ) : (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700">
              未发布 —— 去编排页「发布为智能体」
            </span>
          )
        }
        intro={
          <>
            {graph.kind === 'chatflow' ? '对话型应用' : '工作流应用'}
            发布后用统一扁平端点调用：<strong>key 即应用身份</strong>，路径不再带应用标识。
            一个 <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
              Authorization: Bearer
            </code> 头就够了 —— 包含应用归属、会话隔离、计费维度。
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" asChild>
              <Link to="/api-docs?endpoint=invoke">
                <BookOpen className="mr-1 h-3.5 w-3.5" />
                文档站
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>
              <KeyRound className="mr-1 h-3.5 w-3.5" />
              管理密钥
            </Button>
          </div>
        }
      />
      <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
    </>
  );
};
