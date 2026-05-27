/** 通用 API 文档模版 —— 各服务（智能体 / 知识库 / …）API 文档共用这套外壳
 *
 * 顶栏：标题 + 状态 ·· 通用端点 + 操作（如管理密钥）；正文章节 + 右侧锚点目录（随滚动高亮）。
 * 端点路径 chip 为「相对基址」（不含 /v1，避免与右上角通用端点冗余）；curl 仍给全 URL。
 * 放在 src/api-docs（独立模块，将来可拆为文档站）。
 */
import { useEffect, useRef, useState } from 'react';

import { ArrowLeft, Check, Copy } from 'lucide-react';

import { cn } from '@/core/lib/cn';

export interface ApiDocSection {
  id: string;
  label: string;
  method?: 'GET' | 'POST';
  /** 相对基址的路径（不含 /v1）；鉴权等无端点章节可不传 */
  path?: string;
  desc?: React.ReactNode;
  code: string;
}

interface Props {
  title: string;
  /** 通用端点 / 基址（右上角展示 + 可复制） */
  endpoint: string;
  endpointLabel?: string;
  status?: React.ReactNode;
  intro?: React.ReactNode;
  /** 右上角额外操作（如「管理密钥」按钮 + 其 Modal） */
  actions?: React.ReactNode;
  /** 传则左上角显示「返回」 */
  onBack?: () => void;
  sections: ApiDocSection[];
}

const METHOD_TONE: Record<string, string> = {
  POST: 'bg-emerald-100 text-emerald-700',
  GET: 'bg-sky-100 text-sky-700',
};

export const ApiDocTemplate = ({
  title,
  endpoint,
  endpointLabel = '通用端点',
  status,
  intro,
  actions,
  onBack,
  sections,
}: Props) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(sections[0]?.id ?? '');

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

  const goto = (id: string) =>
    scrollRef.current
      ?.querySelector<HTMLElement>(`[data-sec="${id}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  return (
    <div className="flex h-full flex-col">
      {/* 顶栏 */}
      <div className="flex items-center justify-between gap-3 border-b border-stone-200/70 bg-white/70 px-6 py-2.5 backdrop-blur">
        <div className="flex items-center gap-2.5">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> 返回
            </button>
          )}
          <h1 className="text-[14.5px] font-semibold text-stone-900">{title}</h1>
          {status}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white py-1 pr-1 pl-2.5 shadow-sm">
            <span className="shrink-0 text-[10.5px] text-stone-400">{endpointLabel}</span>
            <code className="max-w-[280px] truncate font-mono text-[12px] text-stone-700">
              {endpoint}
            </code>
            <CopyButton text={endpoint} />
          </div>
          {actions}
        </div>
      </div>

      {/* 正文 + 右侧目录 */}
      <div className="flex min-h-0 flex-1">
        <div ref={scrollRef} className="min-w-0 flex-1 overflow-y-auto scroll-smooth">
          <div className="mx-auto max-w-4xl px-6 py-7">
            {intro && (
              <p className="mb-7 text-[12.5px] leading-relaxed text-stone-500">{intro}</p>
            )}
            {sections.map(s => (
              <section key={s.id} data-sec={s.id} className="mb-8 scroll-mt-4">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="text-[15px] font-semibold text-stone-900">{s.label}</h2>
                  {s.method && (
                    <span
                      className={cn(
                        'rounded px-2 py-0.5 font-mono text-[10.5px] font-bold tracking-wide',
                        METHOD_TONE[s.method],
                      )}
                    >
                      {s.method}
                    </span>
                  )}
                  {s.path && (
                    <code className="rounded-md border border-stone-200 bg-stone-50 px-2 py-0.5 font-mono text-[12.5px] text-stone-700">
                      {s.path}
                    </code>
                  )}
                </div>
                {s.desc && (
                  <p className="mt-1.5 text-[12.5px] leading-relaxed text-stone-500">{s.desc}</p>
                )}
                <div className="mt-3">
                  <Code text={s.code} />
                </div>
              </section>
            ))}
          </div>
        </div>

        {/* 右侧锚点目录（无折叠） */}
        <aside className="w-60 shrink-0 overflow-y-auto border-l border-stone-200/70 px-3 py-7">
          <div className="sticky top-0">
            <div className="mb-2 px-2 text-[11px] font-medium tracking-wide text-stone-400 uppercase">
              目录
            </div>
            <nav className="flex flex-col gap-0.5">
              {sections.map(s => (
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
      </div>
    </div>
  );
};

const Code = ({ text }: { text: string }) => (
  <div className="group relative">
    <pre className="overflow-x-auto rounded-xl bg-stone-900 px-4 py-3.5 font-mono text-[12px] leading-relaxed whitespace-pre text-stone-100 shadow-sm">
      {text}
    </pre>
    <div className="absolute top-2.5 right-2.5">
      <CopyButton text={text} dark />
    </div>
  </div>
);

const CopyButton = ({ text, dark }: { text: string; dark?: boolean }) => {
  const [copied, setCopied] = useState(false);
  const onCopy = () =>
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
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
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
};
