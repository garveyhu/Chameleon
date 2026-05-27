/** 智能体 API 文档（编辑器「访问 API」tab 用）—— 套用通用 ApiDocTemplate
 *
 * 工作流发布为智能体后走统一对外端点（agent_key = graph_key）。
 * 原 graphs/components/views/api-doc-view 迁来此处，与 KB 文档统一在 api-docs 模块管理。
 */
import { useState } from 'react';

import { KeyRound } from 'lucide-react';

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
          Service API 使用 API-Key 鉴权，强烈建议存放在后端、勿泄露到客户端。每个请求都在{' '}
          <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
            Authorization
          </code>{' '}
          头携带。密钥为本智能体的 <strong>agent-</strong> 作用域密钥（右上角「管理密钥」生成）。
        </>
      ),
      code: 'Authorization: Bearer agent-xxxxxxxxxxxxxxxx',
    },
    {
      id: 'detail',
      label: '智能体详情',
      method: 'GET',
      path: `/agents/${key}`,
      desc: '获取该智能体的基本信息（名称、类型、是否在线）。',
      code: `curl '${base}/agents/${key}' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'invoke',
      label: '原生调用',
      method: 'POST',
      path: `/agents/${key}/invoke`,
      desc: '本平台原生协议，返回 answer / session_id / request_id。',
      code: `curl -X POST '${base}/agents/${key}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "input": "你好",\n    "stream": false\n  }'`,
    },
    {
      id: 'stream',
      label: '流式调用 (SSE)',
      method: 'POST',
      path: `/agents/${key}/invoke`,
      desc: '同一端点，body 传 stream:true 即走 SSE。每行 data: {JSON}，末尾 data: [DONE]。',
      code: `curl -N -X POST '${base}/agents/${key}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "input": "你好", "stream": true }'\n\n# 响应（text/event-stream）\ndata: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好", "usage": {...}}\ndata: [DONE]`,
    },
    {
      id: 'openai',
      label: 'OpenAI 兼容',
      method: 'POST',
      path: '/chat/completions',
      desc: '标准 OpenAI 协议，model 传 agent_key。可直接接入 OpenAI SDK / 第三方工具。',
      code: `curl -X POST '${base}/chat/completions' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "model": "${key}",\n    "messages": [\n      {"role": "user", "content": "你好"}\n    ],\n    "stream": false\n  }'`,
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
            发布为智能体后，通过统一对外端点调用（Base URL 见右上角「通用端点」），
            <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
              agent_key = {key}
            </code>
            。所有请求在 Header 携带 API Key。
          </>
        }
        actions={
          <Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>
            <KeyRound className="mr-1 h-3.5 w-3.5" />
            管理密钥
          </Button>
        }
      />
      <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
    </>
  );
};
