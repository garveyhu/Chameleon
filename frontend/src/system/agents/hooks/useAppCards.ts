/** 应用卡片库数据合并 —— 把「图类应用 / 代码·外部应用 / 嵌入渠道」三个来源塌成统一卡片数组
 *
 * 合并口径（去重铁律）：
 *   - 图类应用：graphApi.list() 全量 graph，一图一卡（type 由 kind 推、status 由 published_version 推）
 *   - 代码/外部应用：agentApi.list() 过滤 source≠'graph'（避免与图类重复），一 agent 一卡
 *   - 嵌入标记：embedConfigApi.list() 得到有 embed 的 agent_id 集合；
 *       · 代码/外部卡：直接按 agent.id 命中
 *       · 图类卡：用 agents 里 source='graph' 的项建 graph_id→agent_id 映射，
 *         再判断该 agent_id 是否在 embed 集合
 */
import { useMemo } from 'react';

import { useQuery } from '@tanstack/react-query';

import { type OrchestrationKind, resolveOrchestrationKind } from '@/core/lib/orchestration';
import type { EntityId } from '@/core/types/api';
import { agentApi } from '@/system/agents/services/agent';
import { embedConfigApi } from '@/system/embed_configs/services/embed';
import { graphApi } from '@/system/graphs/services/graph';

export type AppCardSource = 'graph' | 'agent';

/** 统一应用卡片视图模型 */
export interface AppCard {
  /** 卡片唯一标识（graph:{id} / agent:{id}），仅用于 React key */
  cardId: string;
  source: AppCardSource;
  /** 业务实体主键：图类=graph.id；代码/外部=agent.id */
  entityId: EntityId;
  name: string;
  /** 人读标识（graph_key / agent_key） */
  key: string;
  description: string | null;
  /** 头像 data URL（null 用默认按类型图标） */
  icon: string | null;
  kind: OrchestrationKind;
  /** 图类专有：已发布版本号（0 / undefined = 草稿） */
  publishedVersion: number;
  /** 是否已配置嵌入渠道 */
  embedded: boolean;
  /** 嵌入操作目标 agent_id（图类需经 graph→agent 映射得到；为空表示尚不可嵌入） */
  embedAgentId: EntityId | null;
  updatedAt: string;
}

export interface UseAppCardsResult {
  cards: AppCard[];
  isLoading: boolean;
  isError: boolean;
}

export function useAppCards(): UseAppCardsResult {
  const graphsQ = useQuery({ queryKey: ['graphs'], queryFn: () => graphApi.list() });
  const agentsQ = useQuery({ queryKey: ['agents'], queryFn: () => agentApi.list() });
  const embedsQ = useQuery({
    queryKey: ['embed-configs', 'all-for-cards'],
    queryFn: () => embedConfigApi.list({ page: 1, page_size: 100 }),
  });

  const cards = useMemo<AppCard[]>(() => {
    const graphs = graphsQ.data ?? [];
    const agents = agentsQ.data ?? [];
    const embeds = embedsQ.data?.items ?? [];

    // graph_id → agent_id（仅 source='graph' 的 agent 有关联图）
    const graphToAgent = new Map<string, EntityId>();
    for (const a of agents) {
      if (a.source === 'graph' && a.graph_id != null) {
        graphToAgent.set(String(a.graph_id), a.id);
      }
    }
    // 已配置嵌入的 agent_id 集合
    const embeddedAgentIds = new Set(embeds.map(e => String(e.agent_id)));

    const graphCards: AppCard[] = graphs.map(g => {
      const agentId = graphToAgent.get(String(g.id)) ?? null;
      return {
        cardId: `graph:${g.id}`,
        source: 'graph',
        entityId: g.id,
        name: g.name,
        key: g.graph_key,
        description: g.description,
        icon: g.icon ?? null,
        kind: g.kind === 'workflow' ? 'workflow' : 'chatflow',
        publishedVersion: g.published_version ?? 0,
        embedded: agentId != null && embeddedAgentIds.has(String(agentId)),
        embedAgentId: agentId,
        updatedAt: g.updated_at,
      };
    });

    // 代码/外部应用：过滤掉 source='graph'（已由 graphs 出卡，避免重复）
    const agentCards: AppCard[] = agents
      .filter(a => a.source !== 'graph')
      .map(a => ({
        cardId: `agent:${a.id}`,
        source: 'agent',
        entityId: a.id,
        name: a.name,
        key: a.agent_key,
        description: a.description,
        icon: a.icon ?? null,
        kind: resolveOrchestrationKind(a.source, a.graph_kind) ?? 'external',
        publishedVersion: 0,
        embedded: embeddedAgentIds.has(String(a.id)),
        embedAgentId: a.id,
        updatedAt: a.updated_at,
      }));

    return [...graphCards, ...agentCards].sort(
      (x, y) => new Date(y.updatedAt).getTime() - new Date(x.updatedAt).getTime(),
    );
  }, [graphsQ.data, agentsQ.data, embedsQ.data]);

  return {
    cards,
    isLoading: graphsQ.isLoading || agentsQ.isLoading || embedsQ.isLoading,
    isError: graphsQ.isError || agentsQ.isError || embedsQ.isError,
  };
}
