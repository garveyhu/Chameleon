/** 应用详情页 —— 统一「应用详情」tab：概览 / 关联 KB / 关联模型 / 会话 / API / 监测
 *
 * 按 source 显隐：关联 KB / 关联模型仅 source='local'（代码应用）；其余 tab 全应用通用。
 * graph 来源的应用走全屏图编辑器，此页仅作详情聚合（KB / 模型在编排画布配置，故隐藏两 tab）。
 */
import type { ReactElement, ReactNode } from 'react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Code2,
  Cpu,
  Globe,
  Image as ImageIcon,
  Info,
  KeyRound,
  type LucideIcon,
  MessageSquare,
  MessagesSquare,
  Video,
  Workflow,
  Wrench,
} from 'lucide-react';

import { OrchestrationBadge } from '@/core/components/common/orchestration-badge';
import { SectionCard } from '@/core/components/table';
import { Badge } from '@/core/components/ui/badge';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { resolveOrchestrationKind } from '@/core/lib/orchestration';
import { AgentApiTab } from '@/system/agents/components/agent-api-tab';
import { DetailSection } from '@/system/agents/components/detail-section';
import { AgentConfigForm } from '@/system/agents/components/agent-config-form';
import { AgentHelperModelField } from '@/system/agents/components/agent-helper-model-field';
import { AgentOverviewTab } from '@/system/agents/components/agent-overview-tab';
import { AgentSessionsTab } from '@/system/agents/components/agent-sessions-tab';
import { LinkedKbsForm } from '@/system/agents/components/linked-kbs-form';
import { LinkedModelsForm } from '@/system/agents/components/linked-models-form';
import { LinkedToolsForm } from '@/system/agents/components/linked-tools-form';
import { agentApi } from '@/system/agents/services/agent';
import type { AgentItem } from '@/system/agents/types/agent';
import { modelApi } from '@/system/models/services/model';

type TabKey = 'info' | 'kbs' | 'model' | 'tools' | 'sessions' | 'api' | 'monitor';

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
  { key: 'tools', label: '关联工具', icon: <Wrench className="h-3.5 w-3.5" />, localOnly: true },
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
          {tab === 'tools' && isLocal && <LinkedToolsForm agentId={agentId} />}
          {tab === 'sessions' && agent && <AgentSessionsTab agentKey={agent.agent_key} />}
          {tab === 'api' && agent && <AgentApiTab agentId={agentId} agentKey={agent.agent_key} />}
          {tab === 'monitor' && <AgentOverviewTab agentId={agentId} />}
        </div>
      </SectionCard>
    </div>
  );
};

/** kind → 默认头像（用户未上传 icon 时按编排方式给个色） */
const KIND_TILE: Record<
  ReturnType<typeof resolveOrchestrationKind> & string,
  { Icon: LucideIcon; tile: string }
> = {
  code: { Icon: Code2, tile: 'bg-indigo-50 text-indigo-600' },
  chatflow: { Icon: MessageSquare, tile: 'bg-sky-50 text-sky-600' },
  workflow: { Icon: Workflow, tile: 'bg-violet-50 text-violet-600' },
  external: { Icon: Globe, tile: 'bg-amber-50 text-amber-600' },
};

const Header = ({ agent, loading }: { agent: AgentItem | null; loading: boolean }) => {
  const kind = agent ? resolveOrchestrationKind(agent.source, agent.graph_kind) : null;
  const meta = (kind && KIND_TILE[kind]) || KIND_TILE.external;
  const Icon = meta.Icon;
  return (
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
        <div className="flex items-center gap-2.5">
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg',
              agent.icon ? 'bg-stone-100' : meta.tile,
            )}
          >
            {agent.icon ? (
              <img src={agent.icon} alt="" className="h-full w-full object-cover" />
            ) : (
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            )}
          </div>
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
        </div>
      ) : (
        <span className="text-[12.5px] text-stone-400">未找到</span>
      )}
    </div>
  );
};

const EXTERNAL_LABEL: Record<string, string> = {
  dify: 'Dify',
  fastgpt: 'FastGPT',
  coze: 'Coze',
};

/** 定义列表行（label 左·value 右，行间细分隔线） */
const Field = ({
  label,
  value,
  mono,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) => (
  <div className="flex items-start justify-between gap-6 py-2.5">
    <span className="shrink-0 text-[12px] text-stone-400">{label}</span>
    <span
      className={cn(
        'min-w-0 text-right text-[12.5px] break-all text-stone-800',
        mono && 'font-mono',
      )}
    >
      {value}
    </span>
  </div>
);

const StatusPill = ({ enabled }: { enabled: boolean }) => (
  <span
    className={cn(
      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
      enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-stone-100 text-stone-500',
    )}
  >
    <span
      className={cn('h-1.5 w-1.5 rounded-full', enabled ? 'bg-emerald-500' : 'bg-stone-400')}
    />
    {enabled ? '已启用' : '已停用'}
  </span>
);

const GenerationAppInfo = ({ agent }: { agent: AgentItem }) => {
  const modelId = (agent.config as { model_id?: string | number } | null)?.model_id;
  const q = useQuery({ queryKey: ['models', 'all'], queryFn: () => modelApi.list() });
  const model = (q.data ?? []).find(m => String(m.id) === String(modelId));
  const isVideo = model?.kind === 'video';
  const modelLabel = model
    ? `${model.code}${model.provider_code ? `（${model.provider_code}）` : ''}`
    : modelId
      ? `#${modelId}（模型不存在或未启用）`
      : '未绑定';
  return (
    <DetailSection
      icon={isVideo ? Video : ImageIcon}
      title={agent.name}
      desc={isVideo ? '图生视频应用' : '文生图应用'}
    >
      <div className="mb-3 rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2.5 text-[12px] text-violet-700">
        生成类应用：直接调用下方生成模型出{isVideo ? '视频' : '图'}，可在 Playground 关联或经 API 调用。
      </div>
      <div className="divide-y divide-stone-100">
        <Field label="应用标识" value={agent.agent_key} mono />
        <Field label="类型" value={isVideo ? '图生视频' : '文生图'} />
        <Field label="状态" value={<StatusPill enabled={agent.enabled} />} />
        <Field label="生成模型" value={modelLabel} mono />
        {agent.description && <Field label="描述" value={agent.description} />}
        <Field label="创建时间" value={formatDateTime(agent.created_at)} mono />
        <Field label="更新时间" value={formatDateTime(agent.updated_at)} mono />
      </div>
    </DetailSection>
  );
};

const InfoTab = ({ agent }: { agent: AgentItem | null }) => {
  if (!agent) return <div className="py-12 text-center text-sm text-stone-400">—</div>;
  if (agent.source === 'comfyui') return <GenerationAppInfo agent={agent} />;
  const isLocal = agent.source === 'local';
  const isGraph = agent.source === 'graph';
  const isExternal = ['dify', 'fastgpt', 'coze'].includes(agent.source);
  const typeLabel = isLocal
    ? '代码应用'
    : isGraph
      ? agent.graph_kind === 'workflow'
        ? '流程编排应用'
        : '对话编排应用'
      : EXTERNAL_LABEL[agent.source] ?? '外部应用';
  const SectionIcon = isLocal ? Code2 : isGraph ? Workflow : Globe;
  return (
    <div className="space-y-4">
      {isGraph && agent.graph_id != null && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50/60 px-4 py-3">
          <div className="flex items-center gap-2 text-[12px] text-stone-600">
            <Workflow className="h-4 w-4 shrink-0 text-blue-600" />
            <span>
              此应用由<span className="font-medium text-stone-800">工作流编排</span>
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
      {isExternal && (
        <div className="rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3 text-[12px] text-amber-700">
          外部应用：对话流程与凭据在 {typeLabel} 平台维护，此处仅作关联与调用入口。
        </div>
      )}

      <DetailSection icon={SectionIcon} title={agent.name} desc={typeLabel}>
        <div className="divide-y divide-stone-100">
          <Field label="应用标识" value={agent.agent_key} mono />
          <Field label="类型" value={typeLabel} />
          <Field label="状态" value={<StatusPill enabled={agent.enabled} />} />
          {isExternal && (
            <Field label="供应商 ID" value={String(agent.provider_id ?? '—')} mono />
          )}
          {isLocal && <Field label="本地类路径" value={agent.local_class_path ?? '—'} mono />}
          {isLocal && agent.version && <Field label="版本" value={agent.version} mono />}
          {(agent.tags ?? []).length > 0 && (
            <Field
              label="标签"
              value={
                <span className="flex flex-wrap justify-end gap-1">
                  {(agent.tags ?? []).map(t => (
                    <span
                      key={t}
                      className="rounded-full bg-stone-100 px-2 py-0.5 text-[10.5px] text-stone-600"
                    >
                      {t}
                    </span>
                  ))}
                </span>
              }
            />
          )}
          {agent.description && <Field label="描述" value={agent.description} />}
          <Field label="创建时间" value={formatDateTime(agent.created_at)} mono />
          <Field label="更新时间" value={formatDateTime(agent.updated_at)} mono />
        </div>
      </DetailSection>

      {(isLocal || isGraph) && (
        <DetailSection icon={Cpu} title="辅助模型" desc="followup / 标题 / 摘要等辅助调用使用">
          <AgentHelperModelField agent={agent} compact />
        </DetailSection>
      )}
      {/* 代码应用的声明式配置项可在此编辑；外部/编排配置在各自平台/画布 */}
      {isLocal && <AgentConfigForm agentId={agent.id} />}
    </div>
  );
};
