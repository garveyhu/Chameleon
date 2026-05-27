/** 知识库公开 API 文档页（/api-docs/kb/:kbKey）—— 套用通用 ApiDocTemplate
 *
 * 基址为 KB 专属 {origin}/v1/kbs/{kb_key}，路径 chip 相对该基址（/search、/documents…）。
 */
import { useNavigate, useParams } from 'react-router-dom';

import {
  ApiDocTemplate,
  type ApiDocSection,
} from '@/api-docs/components/api-doc-template';

export const KbApiDocPage = () => {
  const { kbKey } = useParams<{ kbKey: string }>();
  const navigate = useNavigate();
  const base = `${window.location.origin}/v1/kbs/${kbKey ?? ''}`;

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
          头携带密钥。密钥为该知识库的 <strong>kbs-</strong> 作用域密钥，在「知识库详情 → 服务
          API」生成，仅对本知识库有效（与应用密钥 / 智能体密钥区分）。
        </>
      ),
      code: 'Authorization: Bearer kbs-xxxxxxxxxxxxxxxx',
    },
    {
      id: 'search',
      label: '检索',
      method: 'POST',
      path: '/search',
      desc: '按 query 检索知识库，返回命中的切块（含向量 / 关键词相似度分项）。',
      code: `curl -X POST '${base}/search' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "query": "如何重置密码",\n    "top_k": 5\n  }'`,
    },
    {
      id: 'list-docs',
      label: '文档列表',
      method: 'GET',
      path: '/documents',
      desc: '分页列出知识库下的文档。query 参数：page、page_size。',
      code: `curl '${base}/documents?page=1&page_size=20' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'get-doc',
      label: '文档详情',
      method: 'GET',
      path: '/documents/{doc_id}',
      desc: '取单篇文档的元信息与处理状态。',
      code: `curl '${base}/documents/123' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
    {
      id: 'create-doc',
      label: '创建文档',
      method: 'POST',
      path: '/documents',
      desc:
        '从文本或 URL 创建文档并异步入库（切块 + 向量化）。source_type=text 传 content；' +
        '=url 传 source_uri。返回 task_id 供轮询状态。',
      code: `curl -X POST '${base}/documents' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "title": "产品 FAQ",\n    "source_type": "text",\n    "content": "问：…\\n答：…"\n  }'`,
    },
    {
      id: 'update-doc',
      label: '更新文档',
      method: 'POST',
      path: '/documents/{doc_id}/update',
      desc: '改文档 title / tags / meta（不触发重新分块）。',
      code: `curl -X POST '${base}/documents/123/update' \\\n  -H 'Authorization: Bearer {API_KEY}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{ "meta": { "author": "张三" } }'`,
    },
    {
      id: 'delete-doc',
      label: '删除文档',
      method: 'POST',
      path: '/documents/{doc_id}/delete',
      desc: '软删文档并清除其切块与向量。',
      code: `curl -X POST '${base}/documents/123/delete' \\\n  -H 'Authorization: Bearer {API_KEY}'`,
    },
  ];

  return (
    <div className="h-[calc(100vh-3.5rem)]">
      <ApiDocTemplate
        title="知识库 API"
        endpoint={base}
        endpointLabel="基址"
        onBack={() => navigate(-1)}
        intro={
          <>
            知识库 <code className="font-mono text-stone-600">{kbKey}</code>{' '}
            的对外接口：检索 + 文档增改删查，按密钥作用域鉴权。基址见右上角，路径相对基址。
          </>
        }
        sections={sections}
      />
    </div>
  );
};
