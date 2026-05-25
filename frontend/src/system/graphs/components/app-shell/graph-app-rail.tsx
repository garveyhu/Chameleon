/** 工作流编辑器左侧应用栏 —— Dify 套路：应用信息 + 二级导航 + Web App/后端API/MCP 卡片
 *
 * 编辑器整屏后，这条栏取代全局后台侧栏，提供「应用级」上下文：
 *   - 应用头：返回 / 图标 / 名称 / 类型切换 / key / 发布状态 / 保存状态
 *   - 二级导航：编排 / 访问 API / 日志 / 监测
 *   - 应用卡片：Web App（对话/嵌入）、后端服务 API（端点+密钥+文档）、MCP（占位）
 */
import {
  Activity,
  ChevronLeft,
  Code2,
  Copy,
  Globe,
  KeyRound,
  Layers,
  type LucideIcon,
  MessageSquare,
  Plug,
  Rocket,
  ScrollText,
  Server,
  Workflow,
} from 'lucide-react';

import { cn } from '@/core/lib/cn';
import { toast } from '@/core/lib/toast';
import { EnumSelect } from '@/system/graphs/components/spec-fields';
import type { GraphDetail, GraphKind } from '@/system/graphs/types/graph';

export type EditorTab = 'orchestrate' | 'api' | 'logs' | 'monitor';

const NAV: { key: EditorTab; label: string; icon: LucideIcon }[] = [
  { key: 'orchestrate', label: '编排', icon: Layers },
  { key: 'api', label: '访问 API', icon: Code2 },
  { key: 'logs', label: '日志', icon: ScrollText },
  { key: 'monitor', label: '监测', icon: Activity },
];

interface Props {
  graph: GraphDetail;
  kind: GraphKind;
  onKindChange: (k: GraphKind) => void;
  tab: EditorTab;
  onTab: (t: EditorTab) => void;
  /** 编辑器内直接开聊（对话调试），不跳转 */
  onOpenChat: () => void;
  onReturn: () => void;
  dirty: boolean;
  saving: boolean;
}

export const GraphAppRail = ({
  graph,
  kind,
  onKindChange,
  tab,
  onTab,
  onOpenChat,
  onReturn,
  dirty,
  saving,
}: Props) => {
  const isChat = kind === 'chatflow';
  const published = (graph.published_version ?? 0) > 0;
  const apiBase = `${window.location.origin}/v1`;

  const copy = (text: string, label: string) => {
    void navigator.clipboard.writeText(text).then(() => toast.success(`${label}已复制`));
  };

  return (
    <aside className="bg-warm-2/50 flex h-screen w-64 shrink-0 flex-col border-r border-stone-200/70">
      {/* 应用头 */}
      <div className="border-b border-stone-200/70 p-3">
        <button
          type="button"
          onClick={onReturn}
          className="mb-2 inline-flex items-center gap-1 text-[11.5px] text-stone-500 transition hover:text-stone-800"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          返回工作流
        </button>
        <div className="flex items-start gap-2.5">
          <span
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
              isChat ? 'bg-violet-100 text-violet-600' : 'bg-sky-100 text-sky-600',
            )}
          >
            {isChat ? <MessageSquare className="h-4 w-4" /> : <Workflow className="h-4 w-4" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold text-stone-900">{graph.name}</div>
            <div className="truncate font-mono text-[10.5px] text-stone-400">{graph.graph_key}</div>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <EnumSelect
            value={kind}
            onChange={v => onKindChange(v as GraphKind)}
            options={[
              { value: 'chatflow', label: '对话型' },
              { value: 'workflow', label: '流程型' },
            ]}
            className="h-6 w-[88px]"
          />
          {published ? (
            <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">
              <Rocket className="h-2.5 w-2.5" /> v{graph.published_version}
            </span>
          ) : (
            <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
              草稿
            </span>
          )}
          <span className="ml-auto text-[10px] text-stone-400">
            {saving ? '保存中…' : dirty ? '未保存' : '已保存'}
          </span>
        </div>
      </div>

      {/* 二级导航 */}
      <nav className="flex flex-col gap-0.5 p-2">
        {NAV.map(n => (
          <button
            key={n.key}
            type="button"
            onClick={() => onTab(n.key)}
            className={cn(
              'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] transition',
              tab === n.key
                ? 'bg-stone-900 text-white'
                : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900',
            )}
          >
            <n.icon className="h-3.5 w-3.5" />
            {n.label}
          </button>
        ))}
      </nav>

      {/* 应用卡片 */}
      <div className="flex-1 space-y-2.5 overflow-y-auto border-t border-stone-200/70 p-2.5">
        {/* Web App / 嵌入 —— 都在编辑器内完成，不跳转 */}
        <Card icon={Globe} title="Web App" tone={isChat ? 'on' : 'off'}>
          <div className="flex gap-1.5">
            <RailAction label="对话页打开" icon={MessageSquare} onClick={onOpenChat} />
            <RailAction label="嵌入接入" icon={Code2} onClick={() => onTab('api')} />
          </div>
        </Card>

        {/* 后端服务 API */}
        <Card icon={Server} title="后端服务 API" tone={isChat ? 'on' : 'off'}>
          <div className="text-[10px] text-stone-500">API 端点</div>
          <button
            type="button"
            onClick={() => copy(apiBase, 'API 端点')}
            className="mt-0.5 flex w-full items-center gap-1 rounded border border-stone-200 bg-white px-1.5 py-1 text-left font-mono text-[10px] text-stone-600 transition hover:bg-stone-50"
          >
            <span className="min-w-0 flex-1 truncate">{apiBase}</span>
            <Copy className="h-3 w-3 shrink-0 opacity-50" />
          </button>
          <div className="mt-1.5 flex gap-1.5">
            <RailAction label="API 文档" icon={Code2} onClick={() => onTab('api')} />
            <RailAction label="API 密钥" icon={KeyRound} onClick={() => onTab('api')} />
          </div>
        </Card>

        {/* MCP 服务（占位） */}
        <Card icon={Plug} title="MCP 服务" tone="off">
          <p className="text-[10.5px] leading-snug text-stone-400">即将支持</p>
        </Card>
      </div>
    </aside>
  );
};

// ── 小组件 ────────────────────────────────────────────────

const Card = ({
  icon: Icon,
  title,
  tone,
  children,
}: {
  icon: LucideIcon;
  title: string;
  tone: 'on' | 'off';
  children: React.ReactNode;
}) => (
  <div className="rounded-lg border border-stone-200 bg-white p-2.5">
    <div className="mb-1.5 flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 text-stone-500" />
      <span className="text-[12px] font-medium text-stone-800">{title}</span>
      <span
        className={cn(
          'ml-auto inline-flex items-center gap-1 text-[10px]',
          tone === 'on' ? 'text-emerald-600' : 'text-stone-400',
        )}
      >
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            tone === 'on' ? 'bg-emerald-500' : 'bg-stone-300',
          )}
        />
        {tone === 'on' ? '可用' : '未启用'}
      </span>
    </div>
    {children}
  </div>
);

const RailAction = ({
  label,
  onClick,
  icon: Icon,
}: {
  label: string;
  onClick: () => void;
  icon: LucideIcon;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex flex-1 items-center justify-center gap-1 rounded-md border border-stone-200 bg-white px-1.5 py-1.5 text-[11px] text-stone-600 transition hover:border-stone-300 hover:bg-stone-50 hover:text-stone-900"
  >
    <Icon className="h-3 w-3 text-stone-400" />
    {label}
  </button>
);
