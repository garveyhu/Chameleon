/** 智能体 API 文档（编辑器「访问 API」tab 用）—— 套用通用 ApiDocTemplate
 *
 * Dify 风扁平契约：key 即应用身份，路径不再带 agent_key 占位。
 * `agent-` 作用域密钥已绑定到本应用，调用方只看 Bearer 头即可识别归属。
 */
import { useState } from 'react';

import { BookOpen, KeyRound } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/core/components/ui/button';
import { ApiDocTemplate } from '@/api-docs/components/api-doc-template';
import { buildAgentApiDocSections } from '@/api-docs/components/agent-api-doc-sections';
import { AgentKeysModal } from '@/system/graphs/components/app-shell/agent-keys-modal';
import type { GraphDetail } from '@/system/graphs/types/graph';

interface Props {
  graph: GraphDetail;
}

export const AgentApiDocView = ({ graph }: Props) => {
  const base = `${window.location.origin}/v1`;
  const key = graph.graph_key;
  const published = (graph.published_version ?? 0) > 0;
  const [keysOpen, setKeysOpen] = useState(false);

  const sections = buildAgentApiDocSections(base, key, '右上角「管理密钥」生成');

  return (
    <>
      <ApiDocTemplate
        title="访问 API"
        endpoint={base}
        sections={sections}
        status={
          published ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              服务运行中
            </span>
          ) : (
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700">
              未发布 —— 去编排页「发布为智能体」
            </span>
          )
        }
        intro={
          <>
            {graph.kind === 'chatflow' ? '对话型应用' : '工作流应用'}
            发布后用统一扁平端点调用：<strong>key 即应用身份</strong>，路径不再带应用标识。
            一个 <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">
              Authorization: Bearer
            </code> 头就够了 —— 包含应用归属、会话隔离、计费维度。
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" asChild>
              <Link to="/api-docs?endpoint=invoke">
                <BookOpen className="mr-1 h-3.5 w-3.5" />
                文档站
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>
              <KeyRound className="mr-1 h-3.5 w-3.5" />
              管理密钥
            </Button>
          </div>
        }
      />
      <AgentKeysModal graphId={graph.id} open={keysOpen} onClose={() => setKeysOpen(false)} />
    </>
  );
};
