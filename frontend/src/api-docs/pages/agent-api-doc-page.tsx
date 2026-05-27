/** 智能体 API 文档页 —— 独立路由 /api-docs/agent/:agentKey
 *
 * 套用通用 ApiDocTemplate。供应用详情页「API」tab 的「查看 API 文档」跳转；
 * 与编辑器内的 AgentApiDocView 同一套端点说明，但此处按 agent_key 独立成页（本地 / 外部 / 图应用通用）。
 */
import { useNavigate, useParams } from 'react-router-dom';

import { ApiDocTemplate, type ApiDocSection } from '@/api-docs/components/api-doc-template';

export const AgentApiDocPage = () => {
  const { agentKey = '' } = useParams<{ agentKey: string }>();
  const navigate = useNavigate();
  const base = `${window.location.origin}/v1`;

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
          头携带。密钥为本应用的 <strong>app-</strong> 作用域密钥（在应用详情「API」tab 生成）。
        </>
      ),
      code: 'Authorization: Bearer app-xxxxxxxxxxxxxxxx',
    },
    {
      id: 'detail',
      label: '应用详情',
      method: 'GET',
      path: `/agents/${agentKey}`,
      desc: '获取该应用的基本信息（名称、类型、是否在线）。',
      code: `curl '${base}/agents/${agentKey}' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'invoke',
      label: '原生调用',
      method: 'POST',
      path: `/agents/${agentKey}/invoke`,
      desc: '本平台原生协议，返回 answer / session_id / request_id。',
      code: `curl -X POST '${base}/agents/${agentKey}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "input": "你好",\n    "stream": false\n  }'`,
    },
    {
      id: 'stream',
      label: '流式调用 (SSE)',
      method: 'POST',
      path: `/agents/${agentKey}/invoke`,
      desc: '同一端点，body 传 stream:true 即走 SSE。每行 data: {JSON}，末尾 data: [DONE]。',
      code: `curl -N -X POST '${base}/agents/${agentKey}/invoke' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "input": "你好", "stream": true }'\n\n# 响应（text/event-stream）\ndata: {"delta": "你"}\ndata: {"delta": "好"}\ndata: {"end": true, "answer": "你好", "usage": {...}}\ndata: [DONE]`,
    },
    {
      id: 'openai',
      label: 'OpenAI 兼容',
      method: 'POST',
      path: '/chat/completions',
      desc: '标准 OpenAI 协议，model 传 agent_key。可直接接入 OpenAI SDK / 第三方工具。',
      code: `curl -X POST '${base}/chat/completions' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "model": "${agentKey}",\n    "messages": [\n      {"role": "user", "content": "你好"}\n    ],\n    "stream": false\n  }'`,
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
    <ApiDocTemplate
      title="访问 API"
      endpoint={base}
      sections={sections}
      onBack={() => navigate(-1)}
      intro={
        <>
          通过统一对外端点调用本应用（Base URL 见右上角「通用端点」），
          <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
            agent_key = {agentKey}
          </code>
          。所有请求在 Header 携带 API Key。
        </>
      }
    />
  );
};
