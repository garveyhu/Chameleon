/** 知识库公开 API 文档页（/api-docs/kb/:kbKey）—— 复用 KbApiDocView
 *
 * 文档内容抽到 KbApiDocView，与 KB 详情「服务 API」tab 共用。本页只负责
 * 按 kb_key 反查 kb（密钥 CRUD 需内部 id）+ 全屏外壳 + 返回。
 */
import { useNavigate, useParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';

import { KbApiDocView } from '@/api-docs/components/kb-api-doc-view';
import { kbApi } from '@/system/kbs/services/kb';

export const KbApiDocPage = () => {
  const { kbKey } = useParams<{ kbKey: string }>();
  const navigate = useNavigate();

  // 文档页只有 kb_key（公开标识），密钥 CRUD 走内部 id —— 列表里按 key 反查拿到 id
  const kbQ = useQuery({
    queryKey: ['kb-by-key', kbKey],
    queryFn: () => kbApi.list({ page_size: 100 }),
    enabled: !!kbKey,
  });
  const kb = kbQ.data?.items.find(k => k.kb_key === kbKey) ?? null;

  return (
    <div className="-mx-3 -my-3 h-screen md:-mx-6 md:-my-4">
      <KbApiDocView kbKey={kbKey ?? ''} kb={kb} onBack={() => navigate(-1)} />
    </div>
  );
};
