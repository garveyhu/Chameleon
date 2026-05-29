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

/** 渠道 → 中文标签 + 色阶（各渠道有区分度，不再一色灰） */
const CHANNEL_META: Record<string, { label: string; cls: string }> = {
  api: { label: 'API', cls: 'bg-blue-50 text-blue-700' },
  openai: { label: 'OpenAI', cls: 'bg-emerald-50 text-emerald-700' },
  embed: { label: '嵌入', cls: 'bg-violet-50 text-violet-700' },
  playground: { label: 'Playground', cls: 'bg-amber-50 text-amber-700' },
  internal: { label: '内部', cls: 'bg-stone-100 text-stone-500' },
};

export const ChannelLabel = ({ channel }: { channel?: CallChannel | null }) => {
  if (!channel) {
    return <span className="text-stone-300">—</span>;
  }
  const meta = CHANNEL_META[channel] ?? { label: channel, cls: 'bg-stone-100 text-stone-600' };
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-[10.5px] ${meta.cls}`}>
      {meta.label}
    </span>
  );
};
