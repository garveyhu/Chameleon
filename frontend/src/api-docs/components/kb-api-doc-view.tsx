/** 知识库 API 文档内容（可复用）—— Dify 风扁平契约
 *
 * **key 即 KB 身份**——`Authorization: Bearer kbs-xxx` 已经唯一标识了这条 key 绑定的 KB，
 * 路径中**不再带** `kb_key` 占位。同一套路对齐 agent 的 `/v1/invoke` + `/v1/info`。
 *
 * 独立文档页（/api-docs/kb/:kbKey）与 KB 详情「服务 API」tab 共用这套内容，
 * 避免重复维护端点章节。右上角「管理密钥」生成本 KB 的 kbs- 作用域密钥。
 */
import { useState } from 'react';

import { BookOpen, KeyRound } from 'lucide-react';
import { Link } from 'react-router-dom';

import { ApiDocTemplate, type ApiDocSection } from '@/api-docs/components/api-doc-template';
import { Button } from '@/core/components/ui/button';
import { KbKeysModal } from '@/system/kbs/components/kb-keys-modal';
import type { KbItem } from '@/system/kbs/types/kb';

interface Props {
  kbKey: string;
  /** 用于「管理密钥」弹窗（需内部 id）；为空则按钮禁用 */
  kb: KbItem | null;
  /** 传则左上角显示「返回」（独立页用；嵌入 tab 时不传） */
  onBack?: () => void;
}

export const KbApiDocView = ({ kbKey, kb, onBack }: Props) => {
  const [keysOpen, setKeysOpen] = useState(false);

  const base = `${window.location.origin}/v1`;

  const sections: ApiDocSection[] = [
    {
      id: 'auth',
      label: '鉴权',
      desc: (
        <>
          所有请求在{' '}
          <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
            Authorization
          </code>{' '}
          头携带密钥。密钥为该知识库的 <strong>kbs-</strong>{' '}
          作用域密钥（右上角「管理密钥」生成），<strong>key 即 KB 身份</strong> —— 已绑定到{' '}
          <code className="font-mono text-[11.5px]">{kbKey}</code>，路径不再带 kb_key 占位。
        </>
      ),
      code: 'Authorization: Bearer kbs-xxxxxxxxxxxxxxxx',
    },
    {
      id: 'info',
      label: '知识库信息',
      method: 'GET',
      path: '/kb',
      desc: '返当前 key 绑定的知识库元信息（kb_key / name / description / embedding_model 等）—— 用于客户端启动时确认 key 代表哪个 KB。',
      code: `curl '${base}/kb' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'search',
      label: '检索',
      method: 'POST',
      path: '/kb/search',
      desc: '按 query 检索知识库，返回命中的切块（含向量 / 关键词相似度分项）。',
      code: `curl -X POST '${base}/kb/search' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "query": "如何重置密码",\n    "top_k": 5\n  }'`,
    },
    {
      id: 'list-docs',
      label: '文档列表',
      method: 'GET',
      path: '/kb/documents',
      desc: '分页列出知识库下的文档。query 参数：page、page_size。',
      code: `curl '${base}/kb/documents?page=1&page_size=20' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'get-doc',
      label: '文档详情',
      method: 'GET',
      path: '/kb/documents/{doc_id}',
      desc: '取单篇文档的元信息与处理状态。',
      code: `curl '${base}/kb/documents/123' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'create-doc',
      label: '创建文档',
      method: 'POST',
      path: '/kb/documents',
      desc:
        '从文本或 URL 创建文档并异步入库（切块 + 向量化）。source_type=text 传 content；' +
        '=url 传 source_uri。返回 task_id 供轮询状态。',
      code: `curl -X POST '${base}/kb/documents' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "title": "产品 FAQ",\n    "source_type": "text",\n    "content": "问：…\\n答：…"\n  }'`,
    },
    {
      id: 'update-doc',
      label: '更新文档',
      method: 'POST',
      path: '/kb/documents/{doc_id}/update',
      desc: '改文档 title / tags / meta（不触发重新分块）。',
      code: `curl -X POST '${base}/kb/documents/123/update' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "meta": { "author": "张三" } }'`,
    },
    {
      id: 'delete-doc',
      label: '删除文档',
      method: 'POST',
      path: '/kb/documents/{doc_id}/delete',
      desc: '软删文档并清除其切块与向量。',
      code: `curl -X POST '${base}/kb/documents/123/delete' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
  ];

  return (
    <>
      <ApiDocTemplate
        title="知识库 API"
        endpoint={base}
        onBack={onBack}
        status={
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            服务运行中
          </span>
        }
        intro={
          <>
            知识库 <code className="font-mono text-stone-600">{kbKey}</code>{' '}
            的对外接口：检索 + 文档增改删查。 <strong>key 即 KB 身份</strong>，路径不再带 kb_key —— 一个{' '}
            <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
              Authorization: Bearer
            </code>{' '}
            头就够了。Base URL 见右上角「通用端点」，下方端点为 /v1 之后的完整路径。
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" asChild>
              <Link to="/api-docs?endpoint=kb.info">
                <BookOpen className="mr-1 h-3.5 w-3.5" />
                文档站
              </Link>
            </Button>
            <Button size="sm" variant="outline" disabled={!kb} onClick={() => setKeysOpen(true)}>
              <KeyRound className="mr-1 h-3.5 w-3.5" />
              管理密钥
            </Button>
          </div>
        }
        sections={sections}
      />
      {kb && <KbKeysModal kbId={kb.id} open={keysOpen} onClose={() => setKeysOpen(false)} />}
    </>
  );
};
