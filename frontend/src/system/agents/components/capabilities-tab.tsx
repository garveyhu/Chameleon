/** 应用「能力」tab —— 只读展示 @agent 在代码里声明的高级能力：消费的外部 MCP、A2A 子智能体
 * allow-list、docker 沙箱隔离、可恢复执行(durable/HITL)。这些能力在代码里定，运营侧只看不改。
 */
import { useQuery } from '@tanstack/react-query';
import { History, Network, Server, ShieldCheck, ShieldOff } from 'lucide-react';

import { DetailSection } from '@/system/agents/components/detail-section';

import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';

interface Props {
  agentId: EntityId;
}

const isUrl = (t: string) => t.startsWith('http://') || t.startsWith('https://');

export const CapabilitiesTab = ({ agentId }: Props) => {
  const capQ = useQuery({
    queryKey: ['agent-capabilities', agentId],
    queryFn: () => agentApi.capabilities(agentId),
  });
  const cap = capQ.data;

  if (capQ.isLoading) {
    return <div className="p-6 text-sm text-stone-400">加载能力…</div>;
  }
  if (!cap) {
    return <div className="p-6 text-sm text-stone-500">无法加载能力信息</div>;
  }
  if (!cap.is_local) {
    return (
      <DetailSection icon={Network} title="高级能力" desc="仅代码声明的 agentkit 应用">
        <div className="px-5 py-4 text-sm text-stone-500">
          外部 / 图编排应用的能力在其各自平台或编排画布中配置，此处不适用。
        </div>
      </DetailSection>
    );
  }

  const hasAny =
    cap.mcp_servers.length > 0 || cap.call_agents.length > 0 || cap.sandboxed || cap.durable;

  return (
    <div className="space-y-4">
      {/* 运行特性徽章：沙箱 / durable */}
      <DetailSection icon={ShieldCheck} title="运行特性" desc="代码声明的隔离与执行语义">
        <div className="flex flex-wrap gap-2.5 px-5 py-4">
          {cap.sandboxed ? (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-[12.5px] font-medium text-amber-700">
              <ShieldCheck className="h-3.5 w-3.5" />
              沙箱隔离 · {cap.trust_tier === 'untrusted' ? '不可信代码（docker）' : cap.trust_tier}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-1.5 text-[12.5px] text-stone-500">
              <ShieldOff className="h-3.5 w-3.5" />
              进程内运行（未声明沙箱）
            </span>
          )}
          {cap.durable && (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[12.5px] font-medium text-emerald-700">
              <History className="h-3.5 w-3.5" />
              可恢复执行 · 人在环(HITL)
            </span>
          )}
        </div>
      </DetailSection>

      {/* 外部 MCP server */}
      <DetailSection
        icon={Server}
        title="外部 MCP"
        desc="消费的外部 MCP server 工具"
        action={<span className="text-[11px] text-stone-400">{cap.mcp_servers.length} 个</span>}
      >
        {cap.mcp_servers.length === 0 ? (
          <div className="px-5 py-4 text-sm text-stone-400">未声明外部 MCP server</div>
        ) : (
          <ul className="divide-y divide-stone-100">
            {cap.mcp_servers.map(s => (
              <li key={s.name} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium text-stone-800">{s.name}</div>
                  {s.url && <div className="truncate text-[11px] text-stone-400">{s.url}</div>}
                </div>
                <span className="shrink-0 rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-500">
                  {s.transport}
                </span>
              </li>
            ))}
          </ul>
        )}
      </DetailSection>

      {/* A2A 子智能体 allow-list */}
      <DetailSection
        icon={Network}
        title="A2A 子智能体"
        desc="可调用的子智能体白名单（进程内 key 或跨系统远程）"
        action={<span className="text-[11px] text-stone-400">{cap.call_agents.length} 个</span>}
      >
        {cap.call_agents.length === 0 ? (
          <div className="px-5 py-4 text-sm text-stone-400">未声明可调用的子智能体</div>
        ) : (
          <ul className="divide-y divide-stone-100">
            {cap.call_agents.map(t => (
              <li key={t} className="flex items-center justify-between gap-3 px-5 py-3">
                <span className="truncate text-[13px] text-stone-700">{t}</span>
                <span
                  className={
                    isUrl(t)
                      ? 'shrink-0 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-600'
                      : 'shrink-0 rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-500'
                  }
                >
                  {isUrl(t) ? '远程 A2A' : '进程内'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </DetailSection>

      {!hasAny && (
        <div className="px-1 text-[12px] text-stone-400">
          此应用未声明高级能力（MCP / A2A / 沙箱 / durable）。在代码里通过 <code>@agent(...)</code>{' '}
          的 <code>mcp_servers</code> / <code>call_agents</code> / <code>sandboxed</code> /{' '}
          <code>durable</code> 参数声明后，这里会展示。
        </div>
      )}
    </div>
  );
};
