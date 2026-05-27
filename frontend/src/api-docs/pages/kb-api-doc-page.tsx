/** 知识库公开 API 文档页（/api-docs/kb/:kbKey）
 *
 * 自成一体：不依赖业务 store / service，纯展示。基址按当前域名 + kb_key 拼。
 * 鉴权用该 KB 的 kbs- 作用域密钥（在 KB 详情页「服务 API」里生成）。
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { ArrowLeft, Check, Copy } from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';

interface Endpoint {
  id: string;
  method: 'GET' | 'POST';
  path: string;
  title: string;
  desc: string;
  curl: (base: string) => string;
}

const AUTH_NOTE =
  '所有请求头带 Authorization: Bearer <你的密钥>。密钥为该知识库的 kbs- 作用域密钥，' +
  '在「知识库详情 → 服务 API」里生成；仅对本知识库有效。';

const ENDPOINTS: Endpoint[] = [
  {
    id: 'search',
    method: 'POST',
    path: '/search',
    title: '检索',
    desc: '按 query 检索知识库，返回命中的切块（含相似度分项）。',
    curl: b =>
      `curl -X POST ${b}/search \\\n  -H "Authorization: Bearer $KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"query":"如何重置密码","top_k":5}'`,
  },
  {
    id: 'list-docs',
    method: 'GET',
    path: '/documents',
    title: '文档列表',
    desc: '分页列出知识库下的文档。query 参数：page、page_size。',
    curl: b => `curl "${b}/documents?page=1&page_size=20" \\\n  -H "Authorization: Bearer $KEY"`,
  },
  {
    id: 'get-doc',
    method: 'GET',
    path: '/documents/{doc_id}',
    title: '文档详情',
    desc: '取单篇文档的元信息与状态。',
    curl: b => `curl ${b}/documents/123 \\\n  -H "Authorization: Bearer $KEY"`,
  },
  {
    id: 'create-doc',
    method: 'POST',
    path: '/documents',
    title: '创建文档',
    desc:
      '从文本或 URL 创建文档并异步入库（切块 + 向量化）。source_type=text 时传 content；' +
      '=url 时传 source_uri。返回 task_id 供轮询。',
    curl: b =>
      `curl -X POST ${b}/documents \\\n  -H "Authorization: Bearer $KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"title":"FAQ","source_type":"text","content":"问：…答：…"}'`,
  },
  {
    id: 'update-doc',
    method: 'POST',
    path: '/documents/{doc_id}/update',
    title: '更新文档',
    desc: '改文档 title / tags / meta（不重新分块）。',
    curl: b =>
      `curl -X POST ${b}/documents/123/update \\\n  -H "Authorization: Bearer $KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{"meta":{"author":"张三"}}'`,
  },
  {
    id: 'delete-doc',
    method: 'POST',
    path: '/documents/{doc_id}/delete',
    title: '删除文档',
    desc: '软删文档并清除其切块与向量。',
    curl: b => `curl -X POST ${b}/documents/123/delete \\\n  -H "Authorization: Bearer $KEY"`,
  },
];

export const KbApiDocPage = () => {
  const { kbKey } = useParams<{ kbKey: string }>();
  const navigate = useNavigate();
  const base = `${window.location.origin}/v1/kbs/${kbKey ?? ''}`;

  return (
    <div className="mx-auto max-w-[920px] px-4 py-2">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-3 inline-flex items-center gap-1 text-[12.5px] text-stone-500 hover:text-stone-800"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> 返回
      </button>

      <h1 className="text-[18px] font-semibold text-stone-900">知识库 API</h1>
      <p className="mt-1 text-[12.5px] text-stone-500">
        知识库 <code className="font-mono text-stone-700">{kbKey}</code> 的对外接口。检索 +
        文档增改删查，按密钥作用域鉴权。
      </p>

      <section className="mt-5">
        <h2 className="mb-2 text-[14px] font-medium text-stone-900">鉴权</h2>
        <p className="mb-2 text-[12.5px] leading-relaxed text-stone-600">{AUTH_NOTE}</p>
        <CodeBlock code={'Authorization: Bearer kbs-xxxxxxxxxxxx'} />
      </section>

      <section className="mt-5">
        <h2 className="mb-2 text-[14px] font-medium text-stone-900">基址</h2>
        <CodeBlock code={base} />
      </section>

      <section className="mt-6">
        <h2 className="mb-3 text-[14px] font-medium text-stone-900">接口</h2>
        <div className="space-y-4">
          {ENDPOINTS.map(ep => (
            <div
              key={ep.id}
              className="rounded-lg border border-stone-200/70 bg-white p-3.5"
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    'rounded px-1.5 py-0.5 font-mono text-[10.5px] font-semibold',
                    ep.method === 'GET'
                      ? 'bg-sky-50 text-sky-700'
                      : 'bg-emerald-50 text-emerald-700',
                  )}
                >
                  {ep.method}
                </span>
                <code className="font-mono text-[12.5px] text-stone-800">{ep.path}</code>
                <span className="ml-2 text-[12.5px] font-medium text-stone-700">{ep.title}</span>
              </div>
              <p className="mt-1.5 text-[11.5px] leading-relaxed text-stone-500">{ep.desc}</p>
              <div className="mt-2">
                <CodeBlock code={ep.curl(base)} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

const CodeBlock = ({ code }: { code: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = () =>
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      toast.success('已复制');
      setTimeout(() => setCopied(false), 1500);
    });
  return (
    <div className="group relative rounded-md border border-stone-200 bg-stone-900/95">
      <button
        type="button"
        onClick={copy}
        className="absolute top-2 right-2 rounded p-1 text-stone-400 opacity-0 transition hover:text-stone-100 group-hover:opacity-100"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      <pre className="overflow-x-auto p-3 text-[11.5px] leading-relaxed text-stone-100">
        <code>{code}</code>
      </pre>
    </div>
  );
};
