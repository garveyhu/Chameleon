/** 应用卡片 —— Dify 风网格卡（图标 + 名称 + 类型徽标 + 描述 + 状态/嵌入标记 + 悬浮操作）
 *
 * 纯展示组件：接 props 出 UI，分流 / 删除 / 嵌入等动作由父页面通过回调注入。
 * 风格对齐知识库卡片网格（kbs-page），配色走主题调色板类。
 */
import {
  Boxes,
  Code2,
  Globe,
  MessageSquare,
  MoreVertical,
  Pencil,
  Trash2,
  Workflow,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/core/components/ui/dropdown-menu';
import { type OrchestrationKind } from '@/core/lib/orchestration';
import { formatRelativeReadable } from '@/core/lib/format';
import type { AppCard as AppCardModel } from '@/system/agents/hooks/useAppCards';

const KIND_META: Record<OrchestrationKind, { label: string; Icon: LucideIcon; badge: string; tile: string }> = {
  code: {
    label: '代码型',
    Icon: Code2,
    badge: 'bg-indigo-50 text-indigo-700',
    tile: 'bg-indigo-50 text-indigo-600',
  },
  chatflow: {
    label: '对话型',
    Icon: MessageSquare,
    badge: 'bg-sky-50 text-sky-700',
    tile: 'bg-sky-50 text-sky-600',
  },
  workflow: {
    label: '流程型',
    Icon: Workflow,
    badge: 'bg-violet-50 text-violet-700',
    tile: 'bg-violet-50 text-violet-600',
  },
  external: {
    label: '外部',
    Icon: Globe,
    badge: 'bg-amber-50 text-amber-700',
    tile: 'bg-amber-50 text-amber-600',
  },
};

interface AppCardProps {
  card: AppCardModel;
  onOpen: (card: AppCardModel) => void;
  onEdit: (card: AppCardModel) => void;
  onEmbed: (card: AppCardModel) => void;
  onDelete: (card: AppCardModel) => void;
}

export const AppCard = ({ card, onOpen, onEdit, onEmbed, onDelete }: AppCardProps) => {
  const meta = KIND_META[card.kind] ?? KIND_META.external;
  const Icon = meta.Icon;
  // 图类应用 + 外部应用可删；代码应用是代码注册的（删了会重新扫描入表），仅可停用
  const canDelete = card.source === 'graph' || card.kind === 'external';

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(card)}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(card);
        }
      }}
      className="group relative flex h-[148px] cursor-pointer flex-col rounded-xl border border-stone-200/80 bg-white p-4 text-left shadow-sm transition hover:border-stone-300 hover:shadow-md"
    >
      {/* 悬浮三点菜单 */}
      <div
        className="absolute right-2 top-2 opacity-0 transition group-hover:opacity-100 data-[open=true]:opacity-100"
        onClick={e => e.stopPropagation()}
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="更多操作"
              className="flex h-7 w-7 items-center justify-center rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-700"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            sideOffset={6}
            className="w-36 rounded-xl border-stone-200/70 p-1 shadow-lg"
          >
            <DropdownMenuItem
              onSelect={() => onEdit(card)}
              className="gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] text-stone-700"
            >
              <Pencil className="h-3.5 w-3.5 text-stone-400" />
              编辑
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => onEmbed(card)}
              disabled={card.embedAgentId == null}
              className="gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] text-stone-700"
            >
              <Boxes className="h-3.5 w-3.5 text-stone-400" />
              {card.embedded ? '管理嵌入' : '嵌入到网页'}
            </DropdownMenuItem>
            {canDelete ? (
              <DropdownMenuItem
                onSelect={() => onDelete(card)}
                className="gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px] text-rose-600 focus:bg-rose-50 focus:text-rose-700"
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-2.5">
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg ${card.icon ? 'bg-stone-100' : meta.tile}`}
        >
          {card.icon ? (
            <img src={card.icon} alt="" className="h-full w-full object-cover" />
          ) : (
            <Icon className="h-5 w-5" strokeWidth={1.75} />
          )}
        </div>
        <div className="min-w-0 flex-1 pr-7">
          <div className="truncate text-[13.5px] font-medium text-stone-900">{card.name}</div>
          <div className="truncate font-mono text-[10.5px] text-stone-400">{card.key}</div>
        </div>
      </div>

      <p className="mt-2 line-clamp-2 flex-1 text-[11.5px] leading-relaxed text-stone-500">
        {card.description || '暂无描述'}
      </p>

      {/* 底部一行：标签（左下）+ 更新时间（右） */}
      <div className="mt-auto flex items-center gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span
            className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.badge}`}
          >
            {meta.label}
          </span>
          {card.source === 'graph' ? (
            card.publishedVersion > 0 ? (
              <span className="inline-flex shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                已发布 v{card.publishedVersion}
              </span>
            ) : (
              <span className="inline-flex shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-500">
                草稿
              </span>
            )
          ) : null}
          {card.embedded ? (
            <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
              已嵌入
            </span>
          ) : null}
        </div>
        <span className="ml-auto shrink-0 truncate text-[11px] text-stone-400">
          更新于 {formatRelativeReadable(card.updatedAt)}
        </span>
      </div>
    </div>
  );
};
