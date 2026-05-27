/** 知识库公开 API 文档页（/api-docs/kb/:kbKey）
 *
 * 自成一体（src/api-docs，零业务耦合，将来可拆为独立文档站）。排版对齐工作流
 * 「访问 API」：顶栏端点 + 右侧锚点目录随滚动高亮 + method 徽章 + 暗色代码块。
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ArrowLeft, Check, Copy } from 'lucide-react';

import { cn } from '@/core/lib/cn';

interface Endpoint {
  id: string;
  method: 'GET' | 'POST';
  path: string;
  title: string;
  desc: string;
  curl: (base: string) => string;
}

const METHOD_TONE: Record<string, string> = {
  POST: 'bg-emerald-100 text-emerald-700',
  GET: 'bg-sky-100 text-sky-700',
};

const ENDPOINTS: Endpoint[] = [
  {
    id: 'search',
    method: 'POST',
    path: '/search',
    title: '检索',
    desc: '按 query 检索知识库，返回命中的切块（含向量 / 关键词相似度分项）。',
    curl: b =>
      `curl -X POST '${b}/search' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "query": "如何重置密码",\n    "top_k": 5\n  }'`,
  },
  {
    id: 'list-docs',
    method: 'GET',
    path: '/documents',
    title: '文档列表',
    desc: '分页列出知识库下的文档。query 参数：page、page_size。',
    curl: b =>
      `curl '${b}/documents?page=1&page_size=20' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'get-doc',
    method: 'GET',
    path: '/documents/{doc_id}',
    title: '文档详情',
    desc: '取单篇文档的元信息与处理状态。',
    curl: b => `curl '${b}/documents/123' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
  {
    id: 'create-doc',
    method: 'POST',
    path: '/documents',
    title: '创建文档',
    desc:
      '从文本或 URL 创建文档并异步入库（切块 + 向量化）。source_type=text 传 content；' +
      '=url 传 source_uri。返回 task_id 供轮询状态。',
    curl: b =>
      `curl -X POST '${b}/documents' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "title": "产品 FAQ",\n    "source_type": "text",\n    "content": "问：…\\n答：…"\n  }'`,
  },
  {
    id: 'update-doc',
    method: 'POST',
    path: '/documents/{doc_id}/update',
    title: '更新文档',
    desc: '改文档 title / tags / meta（不触发重新分块）。',
    curl: b =>
      `curl -X POST '${b}/documents/123/update' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "meta": { "author": "张三" } }'`,
  },
  {
    id: 'delete-doc',
    method: 'POST',
    path: '/documents/{doc_id}/delete',
    title: '删除文档',
    desc: '软删文档并清除其切块与向量。',
    curl: b => `curl -X POST '${b}/documents/123/delete' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
  },
];

export const KbApiDocPage = () => {
  const { kbKey } = useParams<{ kbKey: string }>();
  const navigate = useNavigate();
  const base = `${window.location.origin}/v1/kbs/${kbKey ?? ''}`;

  const scrollRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState('auth');

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
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* 顶栏 */}
      <div className="flex items-center justify-between gap-3 border-b border-stone-200/70 pb-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> 返回
          </button>
          <div>
            <h1 className="text-[15px] font-semibold text-stone-900">知识库 API</h1>
            <p className="text-[11.5px] text-stone-500">
              知识库 <code className="font-mono text-stone-600">{kbKey}</code> 的对外接口
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white py-1 pr-1 pl-2.5 shadow-sm">
          <span className="text-[10.5px] text-stone-400">基址</span>
          <code className="font-mono text-[12px] text-stone-700">{base}</code>
          <CopyButton text={base} />
        </div>
      </div>

      {/* 正文 + 右侧目录 */}
      <div className="flex min-h-0 flex-1">
        <div ref={scrollRef} className="min-w-0 flex-1 overflow-y-auto scroll-smooth pr-2">
          <div className="mx-auto max-w-3xl py-6">
            <Section id="auth" title="鉴权">
              <p className="mb-2.5 text-[12.5px] leading-relaxed text-stone-600">
                所有请求在{' '}
                <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
                  Authorization
                </code>{' '}
                头携带密钥。密钥为该知识库的 <strong>kbs-</strong> 作用域密钥，在「知识库详情 →
                服务 API」生成，仅对本知识库有效（与应用密钥 / 智能体密钥区分）。
              </p>
              <Code text="Authorization: Bearer kbs-xxxxxxxxxxxxxxxx" />
            </Section>

            {ENDPOINTS.map(ep => (
              <Section
                key={ep.id}
                id={ep.id}
                title={ep.title}
                method={ep.method}
                path={ep.path}
                desc={ep.desc}
              >
                <Code text={ep.curl(base)} />
              </Section>
            ))}
          </div>
        </div>

        {/* 右侧锚点目录 */}
        <aside className="w-56 shrink-0 overflow-y-auto border-l border-stone-200/70 py-6 pl-3">
          <div className="sticky top-0">
            <div className="mb-2 px-2 text-[11px] font-medium tracking-wide text-stone-400 uppercase">
              目录
            </div>
            <nav className="flex flex-col gap-0.5">
              {[{ id: 'auth', label: '鉴权' }, ...ENDPOINTS.map(e => ({ id: e.id, label: e.title, method: e.method }))].map(
                s => (
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
                    {'method' in s && s.method && (
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
                ),
              )}
            </nav>
          </div>
        </aside>
      </div>
    </div>
  );
};

const Section = ({
  id,
  title,
  method,
  path,
  desc,
  children,
}: {
  id: string;
  title: string;
  method?: 'GET' | 'POST';
  path?: string;
  desc?: string;
  children: React.ReactNode;
}) => (
  <section data-sec={id} className="mb-8 scroll-mt-4">
    <div className="flex flex-wrap items-center gap-2.5">
      <h2 className="text-[15px] font-semibold text-stone-900">{title}</h2>
      {method && (
        <span
          className={cn(
            'rounded px-2 py-0.5 font-mono text-[10.5px] font-bold tracking-wide',
            METHOD_TONE[method],
          )}
        >
          {method}
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
