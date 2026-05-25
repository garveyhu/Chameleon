/** 访问 API 视图 —— 编辑器内 API 文档页（Dify 套路 + 右侧锚点目录）
 *
 * 工作流发布为智能体后，走统一对外端点（agent_key = graph_key）：
 *   - 智能体详情：GET  /v1/agents/{key}
 *   - 原生调用：  POST /v1/agents/{key}/invoke（stream 由 body 字段控制）
 *   - OpenAI 兼容：POST /v1/chat/completions（model = agent_key）
 *   - 文件上传：  POST /v1/files/presigned-upload
 * 鉴权：Authorization: Bearer <api_key>（在「应用 API Key」页创建）。
 *
 * 顶栏右侧放「通用端点 + 管理密钥」，正文右侧锚点目录随滚动高亮。
 */
import { useEffect, useRef, useState } from 'react';

import { Check, Copy, KeyRound, PanelRightClose, PanelRightOpen } from 'lucide-react';

import { Button } from '@/core/components/ui/button';
import { cn } from '@/core/lib/cn';
import { AgentKeysModal } from '@/system/graphs/components/app-shell/agent-keys-modal';
import type { GraphDetail } from '@/system/graphs/types/graph';

interface Props {
  graph: GraphDetail;
}

interface SecMeta {
  id: string;
  label: string;
  method?: 'GET' | 'POST';
}

const SECTIONS: SecMeta[] = [
  { id: 'sec-auth', label: '鉴权' },
  { id: 'sec-detail', label: '智能体详情', method: 'GET' },
  { id: 'sec-invoke', label: '原生调用', method: 'POST' },
  { id: 'sec-stream', label: '流式调用 (SSE)', method: 'POST' },
  { id: 'sec-openai', label: 'OpenAI 兼容', method: 'POST' },
  { id: 'sec-files', label: '文件上传', method: 'POST' },
];

export const ApiDocView = ({ graph }: Props) => {
  const base = `${window.location.origin}/v1`;
  const key = graph.graph_key;
  const published = (graph.published_version ?? 0) > 0;

  const scrollRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<string>(SECTIONS[0].id);
  const [tocOpen, setTocOpen] = useState(true);
  const [keysOpen, setKeysOpen] = useState(false);

  // 滚动监听 → 高亮目录当前章节（IO 回调里 setState，非 effect 体内同步调用）
  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const els = Array.from(root.querySelectorAll<HTMLElement>('[data-sec]'));
    if (!els.length) return;
    const visible = new Set<string>();
    const io = new IntersectionObserver(
      entries => {
        for (const e of entries) {
          const id = (e.target as HTMLElement).dataset.sec!;
          if (e.isIntersecting) visible.add(id);
          else visible.delete(id);
        }
        const first = els.find(el => visible.has(el.dataset.sec!));
        if (first) setActive(first.dataset.sec!);
      },
      { root, rootMargin: '0px 0px -68% 0px', threshold: [0, 1] },
    );
    els.forEach(el => io.observe(el));
    return () => io.disconnect();
  }, []);

  const goto = (id: string) => {
    scrollRef.current
      ?.querySelector<HTMLElement>(`[data-sec="${id}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="flex h-full flex-col">
      {/* 顶栏：标题 + 状态 ·· 通用端点 + 管理密钥 */}
      <div className="flex items-center justify-between gap-3 border-b border-stone-200/70 bg-white/70 px-8 py-2.5 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <h1 className="text-[14.5px] font-semibold text-stone-900">访问 API</h1>
          {published ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              服务运行中
            </span>
          ) : (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700">
              未发布 —— 去编排页「发布为智能体」
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white py-1 pr-1 pl-2.5 shadow-sm">
            <span className="text-[10.5px] text-stone-400">通用端点</span>
            <code className="font-mono text-[12px] text-stone-700">{base}</code>
            <CopyButton text={base} />
          </div>
          <Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>
            <KeyRound className="mr-1 h-3.5 w-3.5" />
            管理密钥
          </Button>
          <button
            type="button"
            onClick={() => setTocOpen(o => !o)}
            title={tocOpen ? '收起目录' : '展开目录'}
            className="rounded-md border border-stone-200 bg-white p-1.5 text-stone-500 shadow-sm transition hover:bg-stone-50 hover:text-stone-800"
          >
            {tocOpen ? (
              <PanelRightClose className="h-3.5 w-3.5" />
            ) : (
              <PanelRightOpen className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* 正文 + 右侧目录 */}
      <div className="flex min-h-0 flex-1">
        <div ref={scrollRef} className="min-w-0 flex-1 overflow-y-auto scroll-smooth">
          <div className="mx-auto max-w-4xl px-6 py-7">
            <p className="mb-7 text-[12.5px] leading-relaxed text-stone-500">
              {graph.kind === 'chatflow' ? '对话型应用' : '工作流应用'}
              发布为智能体后，通过统一对外端点调用（Base URL 见右上角「通用端点」），
              <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
                agent_key = {key}
              </code>
              。所有请求在 Header 携带 API Key。
            </p>

            <Section meta={SECTIONS[0]}>
              <p className="mb-2.5 text-[12.5px] leading-relaxed text-stone-600">
                Service API 使用 API-Key 鉴权，强烈建议存放在后端、勿泄露到客户端。每个请求都在{' '}
                <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
                  Authorization
                </code>{' '}
                头携带（右上角「管理密钥」生成本智能体专属 Key）：
              </p>
              <Code text="Authorization: Bearer {API_KEY}" />
            </Section>

            <Section
              meta={SECTIONS[1]}
              path={`/v1/agents/${key}`}
              desc="获取该智能体的基本信息（名称、类型、是否在线）。"
            >
              <Code
                text={`curl '${base}/agents/${key}' \\
  -H 'Authorization: Bearer {API_KEY}'`}
              />
            </Section>

            <Section
              meta={SECTIONS[2]}
              path={`/v1/agents/${key}/invoke`}
              desc="本平台原生协议，返回 answer / session_id / request_id。"
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
            </Section>

            <Section
              meta={SECTIONS[3]}
              path={`/v1/agents/${key}/invoke`}
              desc="同一端点，body 传 stream:true 即走 SSE。每行 data: {JSON}，末尾 data: [DONE]。"
            >
              <Code
                text={`curl -N -X POST '${base}/agents/${key}/invoke' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "input": "你好", "stream": true }'

# 响应（text/event-stream）
data: {"delta": "你"}
data: {"delta": "好"}
data: {"end": true, "answer": "你好", "usage": {...}}
data: [DONE]`}
              />
            </Section>

            <Section
              meta={SECTIONS[4]}
              path="/v1/chat/completions"
              desc="标准 OpenAI 协议，model 传 agent_key。可直接接入 OpenAI SDK / 第三方工具。"
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
            </Section>

            <Section
              meta={SECTIONS[5]}
              path="/v1/files/presigned-upload"
              desc="多模态场景：先取预签名地址上传文件，再在调用里引用。"
            >
              <Code
                text={`curl -X POST '${base}/files/presigned-upload' \\
  -H 'Authorization: Bearer {API_KEY}' \\
  -H 'Content-Type: application/json' \\
  -d '{ "filename": "doc.pdf", "content_type": "application/pdf" }'`}
              />
            </Section>
          </div>
        </div>

        {/* 右侧锚点目录（可收起） */}
        {tocOpen && (
          <aside className="w-60 shrink-0 overflow-y-auto border-l border-stone-200/70 px-3 py-7">
            <div className="sticky top-0">
              <div className="mb-2 px-2 text-[11px] font-medium tracking-wide text-stone-400 uppercase">
                目录
              </div>
              <nav className="flex flex-col gap-0.5">
                {SECTIONS.map(s => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => goto(s.id)}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] transition',
                      active === s.id
                        ? 'bg-stone-900 text-white'
                        : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
                    )}
                  >
                    {s.method && (
                      <span
                        className={cn(
                          'rounded px-1 py-0.5 font-mono text-[8.5px] font-bold',
                          active === s.id ? 'bg-white/20 text-white' : METHOD_TONE[s.method],
                        )}
                      >
                        {s.method}
                      </span>
                    )}
                    <span className="truncate">{s.label}</span>
                  </button>
                ))}
              </nav>
            </div>
          </aside>
        )}
      </div>

      <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
    </div>
  );
};

// ── 小组件 ────────────────────────────────────────────────

const METHOD_TONE: Record<string, string> = {
  POST: 'bg-emerald-100 text-emerald-700',
  GET: 'bg-sky-100 text-sky-700',
};

const Section = ({
  meta,
  path,
  desc,
  children,
}: {
  meta: SecMeta;
  path?: string;
  desc?: string;
  children: React.ReactNode;
}) => (
  <section data-sec={meta.id} className="mb-8 scroll-mt-4">
    <div className="flex flex-wrap items-center gap-2.5">
      <h2 className="text-[15px] font-semibold text-stone-900">{meta.label}</h2>
      {meta.method && (
        <span
          className={cn(
            'rounded px-2 py-0.5 font-mono text-[10.5px] font-bold tracking-wide',
            METHOD_TONE[meta.method],
          )}
        >
          {meta.method}
        </span>
      )}
      {path && (
        <code className="rounded-md border border-stone-200 bg-stone-50 px-2 py-0.5 font-mono text-[12.5px] text-stone-700">
          {path}
        </code>
      )}
    </div>
    {desc && <p className="mt-1.5 text-[12.5px] leading-relaxed text-stone-500">{desc}</p>}
    <div className="mt-3">{children}</div>
  </section>
);

const Code = ({ text }: { text: string }) => (
  <div className="group relative">
    <pre className="overflow-x-auto rounded-xl bg-stone-900 px-4 py-3.5 font-mono text-[12px] leading-relaxed text-stone-100 shadow-sm">
      {text}
    </pre>
    <div className="absolute top-2.5 right-2.5">
      <CopyButton text={text} dark />
    </div>
  </div>
);

const CopyButton = ({ text, dark, solid }: { text: string; dark?: boolean; solid?: boolean }) => {
  const [copied, setCopied] = useState(false);
  const onCopy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  if (solid) {
    return (
      <button
        type="button"
        onClick={onCopy}
        title="复制"
        className="flex shrink-0 items-center gap-1 rounded-md bg-stone-900 px-2.5 py-1.5 text-[11.5px] text-white transition hover:bg-stone-700"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
        {copied ? '已复制' : '复制'}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onCopy}
      title="复制"
      className={cn(
        'rounded p-1 transition',
        dark
          ? 'text-stone-400 opacity-0 group-hover:opacity-100 hover:bg-stone-700 hover:text-stone-100'
          : 'text-stone-400 hover:bg-stone-100 hover:text-stone-700',
      )}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
};
