/** 知识库公开 API 文档页（/api-docs/kb/:kbKey）—— 套用通用 ApiDocTemplate
 *
 * 与智能体文档同一模版：右上角展示「通用端点」{origin}/v1，端点 chip 为 /v1 之后的
 * 完整路径（含 /kbs/{kb_key}），curl 给全 URL；右上角「管理密钥」生成本 KB 的 kbs- 密钥。
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';

import {
  ApiDocTemplate,
  type ApiDocSection,
} from '@/api-docs/components/api-doc-template';
import { Button } from '@/core/components/ui/button';
import { KbKeysModal } from '@/system/kbs/components/kb-keys-modal';
import { kbApi } from '@/system/kbs/services/kb';

export const KbApiDocPage = () => {
  const { kbKey } = useParams<{ kbKey: string }>();
  const navigate = useNavigate();
  const [keysOpen, setKeysOpen] = useState(false);

  const base = `${window.location.origin}/v1`;
  const kbPath = `/kbs/${kbKey ?? ''}`;
  const kbBase = `${base}${kbPath}`;

  // 文档页只有 kb_key（公开标识），密钥 CRUD 走内部 id —— 列表里按 key 反查拿到 id
  const kbQ = useQuery({
    queryKey: ['kb-by-key', kbKey],
    queryFn: () => kbApi.list({ page_size: 100 }),
    enabled: !!kbKey,
  });
  const kb = kbQ.data?.items.find(k => k.kb_key === kbKey) ?? null;

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
          头携带密钥。密钥为该知识库的 <strong>kbs-</strong> 作用域密钥（右上角「管理密钥」生成），仅对本知识库有效（与应用密钥 / 智能体密钥区分）。
        </>
      ),
      code: 'Authorization: Bearer kbs-xxxxxxxxxxxxxxxx',
    },
    {
      id: 'search',
      label: '检索',
      method: 'POST',
      path: `${kbPath}/search`,
      desc: '按 query 检索知识库，返回命中的切块（含向量 / 关键词相似度分项）。',
      code: `curl -X POST '${kbBase}/search' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "query": "如何重置密码",\n    "top_k": 5\n  }'`,
    },
    {
      id: 'list-docs',
      label: '文档列表',
      method: 'GET',
      path: `${kbPath}/documents`,
      desc: '分页列出知识库下的文档。query 参数：page、page_size。',
      code: `curl '${kbBase}/documents?page=1&page_size=20' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'get-doc',
      label: '文档详情',
      method: 'GET',
      path: `${kbPath}/documents/{doc_id}`,
      desc: '取单篇文档的元信息与处理状态。',
      code: `curl '${kbBase}/documents/123' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'create-doc',
      label: '创建文档',
      method: 'POST',
      path: `${kbPath}/documents`,
      desc:
        '从文本或 URL 创建文档并异步入库（切块 + 向量化）。source_type=text 传 content；' +
        '=url 传 source_uri。返回 task_id 供轮询状态。',
      code: `curl -X POST '${kbBase}/documents' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "title": "产品 FAQ",\n    "source_type": "text",\n    "content": "问：…\\n答：…"\n  }'`,
    },
    {
      id: 'update-doc',
      label: '更新文档',
      method: 'POST',
      path: `${kbPath}/documents/{doc_id}/update`,
      desc: '改文档 title / tags / meta（不触发重新分块）。',
      code: `curl -X POST '${kbBase}/documents/123/update' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "meta": { "author": "张三" } }'`,
    },
    {
      id: 'delete-doc',
      label: '删除文档',
      method: 'POST',
      path: `${kbPath}/documents/{doc_id}/delete`,
      desc: '软删文档并清除其切块与向量。',
      code: `curl -X POST '${kbBase}/documents/123/delete' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
  ];

  return (
    <div className="-mx-3 -my-3 h-screen md:-mx-6 md:-my-4">
      <ApiDocTemplate
        title="知识库 API"
        endpoint={base}
        onBack={() => navigate(-1)}
        status={
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            服务运行中
          </span>
        }
        intro={
          <>
            知识库 <code className="font-mono text-stone-600">{kbKey}</code>{' '}
            的对外接口：检索 + 文档增改删查，按密钥作用域鉴权。Base URL 见右上角「通用端点」，下方端点为 /v1 之后的完整路径。
          </>
        }
        actions={
          <Button size="sm" variant="outline" disabled={!kb} onClick={() => setKeysOpen(true)}>
            <KeyRound className="mr-1 h-3.5 w-3.5" />
            管理密钥
          </Button>
        }
        sections={sections}
      />
      {kb && <KbKeysModal kbId={kb.id} open={keysOpen} onClose={() => setKeysOpen(false)} />}
    </div>
  );
};
