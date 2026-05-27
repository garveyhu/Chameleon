/** 会话账本徽标 —— 编排方式（kind）与渠道（channel）的语义化标签
 *
 * 纯展示组件：接 props 出 UI，色阶用 Tailwind 调色板类（与全站徽标体系一致）。
 */

import type { AgentSource, CallChannel, GraphKind } from '@/system/call_logs/types/call-log';

interface KindDef {
  label: string;
  /** Tailwind 调色板类（bg + text），按编排方式区分色相 */
  cls: string;
}

/** 由 source + kind 推导「编排方式」展示：
 *   local              → 代码
 *   graph + chatflow   → 对话编排
 *   graph + workflow   → 流程编排
 *   dify / fastgpt / … → 外部
 *   未知（无 agent 记录）→ —
 */
const resolveKind = (
  source: AgentSource | null | undefined,
  kind: GraphKind | null | undefined,
): KindDef | null => {
  if (source === 'local') {
    return { label: '代码', cls: 'bg-indigo-50 text-indigo-700' };
  }
  if (source === 'graph') {
    return kind === 'workflow'
      ? { label: '流程编排', cls: 'bg-violet-50 text-violet-700' }
      : { label: '对话编排', cls: 'bg-sky-50 text-sky-700' };
  }
  if (source === 'dify' || source === 'fastgpt' || source === 'coze') {
    return { label: '外部', cls: 'bg-amber-50 text-amber-700' };
  }
  return null;
};

export const KindBadge = ({
  source,
  kind,
}: {
  source?: AgentSource | null;
  kind?: GraphKind | null;
}) => {
  const def = resolveKind(source, kind);
  if (!def) {
    return <span className="text-[10.5px] text-stone-300">—</span>;
  }
  return (
    <span
      className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${def.cls}`}
    >
      {def.label}
    </span>
  );
};

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
