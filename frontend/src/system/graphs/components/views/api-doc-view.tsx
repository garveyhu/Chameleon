/** 访问 API 视图 —— 编辑器内 API 文档页（Dify 套路）
 *
 * 工作流发布为智能体后，走统一对外端点（agent_key = graph_key）：
 *   - OpenAI 兼容：POST /v1/chat/completions（model = agent_key）
 *   - 原生 invoke：POST /v1/agents/{key}/invoke
 *   - 文件上传：POST /v1/files/presigned-upload
 * 鉴权：Authorization: Bearer <api_key>（在「应用 API Key」页创建）。
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Check, Copy, KeyRound } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import type { GraphDetail } from '@/system/graphs/types/graph';

interface Props {
  graph: GraphDetail;
}

export const ApiDocView = ({ graph }: Props) => {
  const nav = useNavigate();
  const base = `${window.location.origin}/v1`;
  const key = graph.graph_key;
  const published = (graph.published_version ?? 0) > 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-10 py-8">
        <header className="mb-6">
          <h1 className="text-[20px] font-semibold text-stone-900">
            {graph.kind === 'chatflow' ? '对话型应用 API' : '工作流应用 API'}
          </h1>
          <p className="mt-1 text-[12.5px] text-stone-500">
            发布为智能体后，可通过统一对外端点调用（agent_key ={' '}
            <code className="font-mono text-stone-700">{key}</code>）。
            {!published && (
              <span className="ml-1 text-amber-600">
                · 当前未发布，先在编排页点「发布为智能体」。
              </span>
            )}
          </p>
        </header>

        <Block title="Base URL">
          <Code text={base} />
        </Block>

        <Block title="鉴权（Authentication）">
          <p className="mb-2 text-[12.5px] leading-relaxed text-stone-600">
            所有请求在 HTTP Header 携带 API Key：
          </p>
          <Code text="Authorization: Bearer {API_KEY}" />
          <Button size="sm" variant="outline" className="mt-2" onClick={() => nav('/apps')}>
            <KeyRound className="mr-1 h-3 w-3" />
            创建 / 管理 API 密钥
          </Button>
        </Block>

        <Block
          title="OpenAI 兼容 · Chat Completions"
          desc="标准 OpenAI 协议，model 传 agent_key 即可。适合直接接入 OpenAI SDK / 第三方工具。"
          method="POST"
          path="/v1/chat/completions"
        >
          <Code
            text={`curl -X POST '${base}/chat/completions' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "${key}",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "stream": false
  }'`}
          />
        </Block>

        <Block
          title="原生调用 · Agent Invoke"
          desc="本平台原生协议，返回 answer / session_id / request_id。stream=true 走 SSE 流式。"
          method="POST"
          path={`/v1/agents/${key}/invoke`}
        >
          <Code
            text={`curl -X POST '${base}/agents/${key}/invoke' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{
    "input": "你好",
    "stream": false
  }'`}
          />
        </Block>

        <Block
          title="文件上传"
          desc="多模态场景：先取预签名地址上传文件，再在调用里引用。"
          method="POST"
          path="/v1/files/presigned-upload"
        >
          <Code
            text={`curl -X POST '${base}/files/presigned-upload' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "filename": "doc.pdf", "content_type": "application/pdf" }'`}
          />
        </Block>
      </div>
    </div>
  );
};

// ── 小组件 ────────────────────────────────────────────────

const METHOD_TONE: Record<string, string> = {
  POST: 'bg-emerald-100 text-emerald-700',
  GET: 'bg-sky-100 text-sky-700',
};

const Block = ({
  title,
  desc,
  method,
  path,
  children,
}: {
  title: string;
  desc?: string;
  method?: string;
  path?: string;
  children: React.ReactNode;
}) => (
  <section className="mb-7">
    <h2 className="text-[14px] font-medium text-stone-900">{title}</h2>
    {(method || path) && (
      <div className="mt-1.5 flex items-center gap-2">
        {method && (
          <span
            className={cn(
              'rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold',
              METHOD_TONE[method] ?? 'bg-stone-100 text-stone-600',
            )}
          >
            {method}
          </span>
        )}
        {path && <code className="font-mono text-[12px] text-stone-600">{path}</code>}
      </div>
    )}
    {desc && <p className="mt-1.5 text-[12.5px] leading-relaxed text-stone-500">{desc}</p>}
    <div className="mt-2.5">{children}</div>
  </section>
);

const Code = ({ text }: { text: string }) => {
  const [copied, setCopied] = useState(false);
  const onCopy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-lg bg-stone-900 px-3.5 py-3 font-mono text-[12px] leading-relaxed text-stone-100">
        {text}
      </pre>
      <button
        type="button"
        onClick={onCopy}
        title="复制"
        className="absolute top-2 right-2 rounded p-1 text-stone-400 opacity-0 transition group-hover:opacity-100 hover:bg-stone-700 hover:text-stone-100"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
};
