/** 应用详情「API」tab —— 该应用的专属密钥管理 + API 文档入口
 *
 * 密钥复用 AppKeysPanel（与图编辑器同款）；文档跳 api-docs 模块的智能体文档页。
 */
import { BookOpen, KeyRound } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { EntityId } from '@/core/types/api';
import { AppKeysPanel } from '@/system/agents/components/app-keys-panel';
import { DetailSection } from '@/system/agents/components/detail-section';
import { agentApi } from '@/system/agents/services/agent';

interface Props {
  agentId: EntityId;
  agentKey: string;
}

export const AgentApiTab = ({ agentId, agentKey }: Props) => (
  <DetailSection
    icon={KeyRound}
    title="API 密钥"
    desc="仅对本应用有效，用于经 API / 嵌入式调用"
    action={
      <Link
        to={`/api-docs/agent/${encodeURIComponent(agentKey)}`}
        className="inline-flex items-center gap-1 rounded-md border border-stone-200 px-2.5 py-1 text-[12px] font-medium text-stone-600 transition hover:bg-stone-50 hover:text-stone-900"
      >
        <BookOpen className="h-3.5 w-3.5" />
        API 文档
      </Link>
    }
  >
    <AppKeysPanel
      queryKey={['agent-api-keys', agentId]}
      keysApi={{
        list: () => agentApi.listApiKeys(agentId),
        create: name => agentApi.createApiKey(agentId, name),
        revoke: keyId => agentApi.revokeApiKey(agentId, keyId),
      }}
    />
  </DetailSection>
);
