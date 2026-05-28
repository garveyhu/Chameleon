/** 应用详情页 —— 统一「应用详情」tab：概览 / 关联 KB / 关联模型 / 会话 / API / 监测
 *
 * 按 source 显隐：关联 KB / 关联模型仅 source='local'（代码应用）；其余 tab 全应用通用。
 * graph 来源的应用走全屏图编辑器，此页仅作详情聚合（KB / 模型在编排画布配置，故隐藏两 tab）。
 */
import type { ReactElement } from 'react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';
import { Activity, ArrowLeft, ArrowRight, BookOpen, Cpu, Info, KeyRound, MessagesSquare, Workflow } from 'lucide-react';

import { OrchestrationBadge } from '@/core/components/common/orchestration-badge';
import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { AgentApiTab } from '@/system/agents/components/agent-api-tab';
import { AgentConfigForm } from '@/system/agents/components/agent-config-form';
import { AgentHelperModelField } from '@/system/agents/components/agent-helper-model-field';
import { AgentOverviewTab } from '@/system/agents/components/agent-overview-tab';
import { AgentSessionsTab } from '@/system/agents/components/agent-sessions-tab';
import { LinkedKbsForm } from '@/system/agents/components/linked-kbs-form';
import { LinkedModelsForm } from '@/system/agents/components/linked-models-form';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';

type TabKey = 'info' | 'kbs' | 'model' | 'sessions' | 'api' | 'monitor';

interface TabDef {
  key: TabKey;
  label: string;
  icon: ReactElement;
  /** 仅代码应用（source='local'）展示 */
  localOnly?: boolean;
}

const TABS: TabDef[] = [
  { key: 'info', label: '概览', icon: <Info className="h-3.5 w-3.5" /> },
  { key: 'kbs', label: '关联 KB', icon: <BookOpen className="h-3.5 w-3.5" />, localOnly: true },
  { key: 'model', label: '关联模型', icon: <Cpu className="h-3.5 w-3.5" />, localOnly: true },
  { key: 'sessions', label: '会话', icon: <MessagesSquare className="h-3.5 w-3.5" /> },
  { key: 'api', label: 'API', icon: <KeyRound className="h-3.5 w-3.5" /> },
  { key: 'monitor', label: '监测', icon: <Activity className="h-3.5 w-3.5" /> },
];

export const AgentDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const agentId = id ?? '';
  const [tab, setTab] = useState<TabKey>('info');

  const agentQ = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => agentApi.get(agentId),
    enabled: !!agentId,
  });

  const agent = agentQ.data ?? null;
  // 关联 KB / 模型仅代码应用有意义（外部应用在其平台配，图应用在编排画布配）
  const isLocal = agent?.source === 'local';
  const visibleTabs = TABS.filter(t => !t.localOnly || isLocal);

  if (!agentId) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的应用编号</div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-3">
      <Header agent={agent} loading={agentQ.isLoading} />
      <SectionCard className="!p-0">
        <nav className="bg-warm-2/40 flex items-center gap-1 border-b border-stone-200/70 px-3 py-2">
          {visibleTabs.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition',
                tab === t.key
                  ? 'bg-white text-stone-900 shadow-sm'
                  : 'text-stone-500 hover:bg-stone-100 hover:text-stone-800',
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>
        <div className="p-4">
          {tab === 'info' && <InfoTab agent={agent} />}
          {tab === 'kbs' && isLocal && <LinkedKbsForm agentId={agentId} />}
          {tab === 'model' && isLocal && <LinkedModelsForm agentId={agentId} />}
          {tab === 'sessions' && agent && <AgentSessionsTab agentKey={agent.agent_key} />}
          {tab === 'api' && agent && <AgentApiTab agentId={agentId} agentKey={agent.agent_key} />}
          {tab === 'monitor' && <AgentOverviewTab agentId={agentId} />}
        </div>
      </SectionCard>
    </div>
  );
};

const Header = ({ agent, loading }: { agent: AgentItem | null; loading: boolean }) => (
  <div className="flex items-center gap-3">
    <Link
      to="/agents"
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> 应用
    </Link>
    <span className="text-stone-300">/</span>
    {loading ? (
      <span className="text-[12.5px] text-stone-400">加载中…</span>
    ) : agent ? (
      <div className="flex items-baseline gap-2">
        <span className="text-[15px] font-medium text-stone-900">{agent.name}</span>
        <span className="font-mono text-[11.5px] text-stone-500">{agent.agent_key}</span>
        <OrchestrationBadge source={agent.source} graphKind={agent.graph_kind} />
        {!agent.enabled && (
          <Badge variant="outline" className="bg-stone-100 text-[10.5px] text-stone-500">
            已停用
          </Badge>
        )}
      </div>
    ) : (
      <span className="text-[12.5px] text-stone-400">未找到</span>
    )}
  </div>
);

const InfoTab = ({ agent }: { agent: AgentItem | null }) => {
  if (!agent) return <div className="py-12 text-center text-sm text-stone-400">—</div>;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 text-[12.5px]">
        {agent.source === 'graph' && agent.graph_id != null && (
          <div className="col-span-2 flex items-center justify-between gap-3 rounded-md border border-blue-200 bg-blue-50/60 px-3 py-2.5">
            <div className="flex items-center gap-2 text-[12px] text-stone-600">
              <Workflow className="h-4 w-4 shrink-0 text-blue-600" />
              <span>
                此智能体由<span className="font-medium text-stone-800">工作流编排</span>
                驱动，知识库 / 模型在编排画布的节点里配置。
              </span>
            </div>
            <Link
              to={`/graphs/${agent.graph_id}/edit`}
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11.5px] font-medium text-white transition hover:bg-blue-700"
            >
              去工作流编排
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}
        <Kv label="agent_key" value={agent.agent_key} mono />
        <Kv label="source" value={agent.source} />
        <Kv label="状态" value={agent.enabled ? '已启用' : '已停用'} />
        <Kv label="provider_id" value={String(agent.provider_id ?? '—')} mono />
        <Kv label="local_class_path" value={agent.local_class_path ?? '—'} mono />
        <Kv label="version" value={agent.version ?? '—'} mono />
        <AgentHelperModelField agent={agent} />
        <Kv label="tags" value={(agent.tags ?? []).join(', ') || '—'} />
        <Kv label="config" value={agent.config ? JSON.stringify(agent.config) : '—'} mono full />
        <Kv label="description" value={agent.description ?? '—'} full />
        <Kv label="created_at" value={formatDateTime(agent.created_at)} mono />
        <Kv label="updated_at" value={formatDateTime(agent.updated_at)} mono />
      </div>
      <AgentConfigForm agentId={agent.id} />
    </>
  );
};

const Kv = ({
  label,
  value,
  mono,
  full,
}: {
  label: string;
  value: string;
  mono?: boolean;
  full?: boolean;
}) => (
  <div
    className={cn('rounded-md border border-stone-200/70 bg-white px-3 py-2', full && 'col-span-2')}
  >
    <div className="text-[11px] text-stone-500">{label}</div>
    <div className={cn('mt-0.5 text-[12.5px] break-all text-stone-800', mono && 'tnum font-mono')}>
      {value}
    </div>
  </div>
);
