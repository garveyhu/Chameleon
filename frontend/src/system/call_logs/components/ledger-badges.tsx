/** 会话账本徽标 —— 编排方式（kind）与渠道（channel）的语义化标签
 *
 * 纯展示组件：接 props 出 UI，色阶用 Tailwind 调色板类（与全站徽标体系一致）。
 */

import { OrchestrationBadge } from '@/core/components/common/orchestration-badge';
import type { AgentSource, CallChannel, GraphKind } from '@/system/call_logs/types/call-log';

/** 由 source + kind 推导「编排方式」展示（代码 / 对话编排 / 流程编排 / 外部）。 */
export const KindBadge = ({
  source,
  kind,
}: {
  source?: AgentSource | null;
  kind?: GraphKind | null;
}) => <OrchestrationBadge source={source} graphKind={kind} />;

const CHANNEL_LABEL: Record<string, string> = {
  api: 'API',
  openai: 'OpenAI',
  embed: '嵌入',
  playground: 'Playground',
  internal: '内部',
};

export const ChannelLabel = ({ channel }: { channel?: CallChannel | null }) => {
  if (!channel) {
    return <span className="text-stone-300">—</span>;
  }
  const label = CHANNEL_LABEL[channel] ?? channel;
  return (
    <span className="inline-flex rounded bg-stone-100 px-1.5 py-0.5 text-[10.5px] text-stone-600">
      {label}
    </span>
  );
};
