/** Agent 详情页 —— tabs：基础信息 / 关联 KB / 关联模型 / 调用统计 */

import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, BarChart3, BookOpen, Cpu, Info } from 'lucide-react';
import type { ReactElement } from 'react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { LinkedKbsForm } from '@/system/agents/components/linked-kbs-form';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';

type TabKey = 'info' | 'kbs' | 'model' | 'stats';

interface TabDef {
  key: TabKey;
  label: string;
  icon: ReactElement;
}

const TABS: TabDef[] = [
  { key: 'info', label: '基础信息', icon: <Info className="h-3.5 w-3.5" /> },
  { key: 'kbs', label: '关联 KB', icon: <BookOpen className="h-3.5 w-3.5" /> },
  { key: 'model', label: '关联模型', icon: <Cpu className="h-3.5 w-3.5" /> },
  { key: 'stats', label: '调用统计', icon: <BarChart3 className="h-3.5 w-3.5" /> },
];

export const AgentDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const agentId = Number(id);
  const [tab, setTab] = useState<TabKey>('info');

  const agentQ = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => agentApi.get(agentId),
    enabled: Number.isFinite(agentId),
  });

  if (!Number.isFinite(agentId)) {
    return (
      <SectionCard>
        <div className="p-6 text-sm text-stone-500">非法的 agent 编号</div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-3">
      <Header agent={agentQ.data ?? null} loading={agentQ.isLoading} />
      <SectionCard className="!p-0">
        <nav className="flex items-center gap-1 border-b border-stone-200/70 bg-warm-2/40 px-3 py-2">
          {TABS.map(t => (
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
          {tab === 'info' && <InfoTab agent={agentQ.data ?? null} />}
          {tab === 'kbs' && <LinkedKbsForm agentId={agentId} />}
          {tab === 'model' && <PlaceholderTab hint="后续接入默认 LLM 选择" />}
          {tab === 'stats' && <PlaceholderTab hint="待 call_logs 趋势接入" />}
        </div>
      </SectionCard>
    </div>
  );
};

const Header = ({
  agent,
  loading,
}: {
  agent: AgentItem | null;
  loading: boolean;
}) => (
  <div className="flex items-center gap-3">
    <Link
      to="/agents"
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12.5px] text-stone-500 hover:bg-stone-100 hover:text-stone-800"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> 智能体
    </Link>
    <span className="text-stone-300">/</span>
    {loading ? (
      <span className="text-[12.5px] text-stone-400">加载中…</span>
    ) : agent ? (
      <div className="flex items-baseline gap-2">
        <span className="text-[15px] font-medium text-stone-900">{agent.name}</span>
        <span className="font-mono text-[11.5px] text-stone-500">
          {agent.agent_key}
        </span>
        <Badge variant="outline" className="text-[10.5px]">
          {agent.source}
        </Badge>
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
    <div className="grid grid-cols-2 gap-3 text-[12.5px]">
      <Kv label="agent_key" value={agent.agent_key} mono />
      <Kv label="source" value={agent.source} />
      <Kv label="状态" value={agent.enabled ? '已启用' : '已停用'} />
      <Kv label="provider_id" value={String(agent.provider_id ?? '—')} mono />
      <Kv
        label="local_class_path"
        value={agent.local_class_path ?? '—'}
        mono
      />
      <Kv label="version" value={agent.version ?? '—'} mono />
      <Kv label="default_model_id" value={String(agent.default_model_id ?? '—')} mono />
      <Kv label="tags" value={(agent.tags ?? []).join(', ') || '—'} />
      <Kv
        label="config"
        value={agent.config ? JSON.stringify(agent.config) : '—'}
        mono
        full
      />
      <Kv label="description" value={agent.description ?? '—'} full />
      <Kv label="created_at" value={formatDateTime(agent.created_at)} mono />
      <Kv label="updated_at" value={formatDateTime(agent.updated_at)} mono />
    </div>
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
  <div className={cn('rounded-md border border-stone-200/70 bg-white px-3 py-2', full && 'col-span-2')}>
    <div className="text-[11px] text-stone-500">{label}</div>
    <div
      className={cn(
        'mt-0.5 break-all text-[12.5px] text-stone-800',
        mono && 'font-mono tnum',
      )}
    >
      {value}
    </div>
  </div>
);

const PlaceholderTab = ({ hint }: { hint: string }) => (
  <div className="flex h-[200px] flex-col items-center justify-center gap-2 text-stone-400">
    <div className="text-[12.5px]">{hint}</div>
  </div>
);
