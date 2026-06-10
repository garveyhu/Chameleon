/** 智能体 API 文档页 —— 独立路由 /api-docs/agent/:agentKey
 *
 * Dify 风扁平契约：key 即应用身份，路径不再带 agent_key 占位。
 * 本地代码 / 外部 / 图应用通用 —— 同一套扁平端点说明。
 * agent_key 仅作为右上角"绑定到此应用"展示用，不进路径。
 */
import { BookOpen } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ApiDocTemplate } from '@/api-docs/components/api-doc-template';
import { buildAgentApiDocSections } from '@/api-docs/components/agent-api-doc-sections';
import { Button } from '@/core/components/ui/button';

export const AgentApiDocPage = () => {
  const { agentKey = '' } = useParams<{ agentKey: string }>();
  const navigate = useNavigate();
  const base = `${window.location.origin}/v1`;

  const sections = buildAgentApiDocSections(base, agentKey, '在应用详情「API」tab 生成');

  return (
    <ApiDocTemplate
      title="访问 API"
      endpoint={base}
      sections={sections}
      onBack={() => navigate(-1)}
      intro={
        <>
          用统一扁平端点调用：<strong>key 即应用身份</strong>，路径不再带应用标识。
          本应用绑定的 key 已锁定到 <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">{agentKey}</code>，
          一个 <code className="rounded bg-stone-100 px-1 py-0.5 font-mono text-[11.5px] text-stone-700">Authorization: Bearer</code> 头就够。
        </>
      }
      actions={
        <Button size="sm" variant="ghost" asChild>
          <Link to="/api-docs?endpoint=invoke">
            <BookOpen className="mr-1 h-3.5 w-3.5" />
            文档站
          </Link>
        </Button>
      }
    />
  );
};
