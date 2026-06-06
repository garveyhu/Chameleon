/** ModelCard —— 单个逻辑模型的现代卡片。
 *
 * 取代模型表格行：品牌图标 + code + 上游映射 + 能力 chips + 运行参数 + 行内操作。
 * provider 被删（__deleted_*）的孤儿模型用红边 + 告警提示。
 */

import {
  AlertTriangle,
  Braces,
  Eye,
  SlidersHorizontal,
  Star,
  Trash2,
  Wrench,
  Zap,
} from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';

import { ProviderAvatar } from '@/core/components/common/provider-avatar';
import { Switch } from '@/core/components/ui/switch';
import { cn } from '@/core/lib/cn';
import type { ModelItem } from '@/system/models/types/model';

interface Props {
  model: ModelItem;
  isDefault: boolean;
  onConfig: () => void;
  onTest: () => void;
  onDelete: () => void;
  onToggle: (enabled: boolean) => void;
  onSetDefault: () => void;
}

const CHIP_TONE = {
  primary: 'bg-primary-50 text-primary-700',
  violet: 'bg-violet-50 text-violet-700',
  sky: 'bg-sky-50 text-sky-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  muted: 'bg-stone-100 text-stone-500',
} as const;

const Chip = ({
  tone = 'muted',
  icon: Icon,
  children,
}: {
  tone?: keyof typeof CHIP_TONE;
  icon?: ComponentType<{ className?: string }>;
  children: ReactNode;
}) => (
  <span
    className={cn(
      'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10.5px] font-medium',
      CHIP_TONE[tone],
    )}
  >
    {Icon && <Icon className="h-3 w-3" />}
    {children}
  </span>
);

const fmtCtx = (n: number): string =>
  n >= 1000 ? `${Math.round(n / 1000)}K` : String(n);

const ActionBtn = ({
  icon: Icon,
  label,
  onClick,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
  >
    <Icon className="h-3.5 w-3.5" /> {label}
  </button>
);

export const ModelCard = ({
  model,
  isDefault,
  onConfig,
  onTest,
  onDelete,
  onToggle,
  onSetDefault,
}: Props) => {
  const orphan = (model.provider_code || '').startsWith('__deleted');
  const caps = model.capabilities || {};
  const d = model.defaults || {};
  const upstream =
    model.upstream_name && model.upstream_name !== model.code
      ? model.upstream_name
      : null;

  return (
    <div
      className={cn(
        'group flex flex-col rounded-xl border bg-[var(--color-paper)] p-4 transition hover:-translate-y-0.5 hover:shadow-pop',
        orphan ? 'border-red-200' : 'border-stone-200 hover:border-stone-300',
        !model.enabled && 'opacity-65',
      )}
    >
      <div className="flex items-start gap-2.5">
        <ProviderAvatar code={model.provider_code} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[13px] font-semibold text-stone-900">
            {model.code}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-stone-400">
            {orphan ? (
              <span className="inline-flex items-center gap-1 text-red-500">
                <AlertTriangle className="h-3 w-3" /> provider 已删
              </span>
            ) : (
              <span className="truncate">{model.provider_code || '?'}</span>
            )}
            {upstream && (
              <span className="truncate text-stone-400" title={`经网关上游名: ${upstream}`}>
                · ↗ <span className="font-mono">{upstream}</span>
              </span>
            )}
          </div>
        </div>
        <Switch checked={model.enabled} onCheckedChange={onToggle} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {isDefault && (
          <Chip tone="primary" icon={Star}>
            默认
          </Chip>
        )}
        {model.kind === 'chat' && typeof caps.context_window === 'number' && (
          <Chip tone="primary">{fmtCtx(caps.context_window)} ctx</Chip>
        )}
        {model.kind === 'chat' && caps.vision && (
          <Chip tone="violet" icon={Eye}>
            视觉
          </Chip>
        )}
        {model.kind === 'chat' && caps.tool_call && (
          <Chip tone="sky" icon={Wrench}>
            工具
          </Chip>
        )}
        {model.kind === 'chat' && caps.json_mode && (
          <Chip tone="emerald" icon={Braces}>
            JSON
          </Chip>
        )}
        {model.kind === 'embedding' && model.dim != null && <Chip>{model.dim} 维</Chip>}
        {typeof d.temperature === 'number' && <Chip>temp {d.temperature}</Chip>}
        {typeof d.max_tokens === 'number' && <Chip>max {d.max_tokens}</Chip>}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-stone-100 pt-2.5">
        <div className="flex items-center gap-0.5">
          <ActionBtn icon={SlidersHorizontal} label="配置" onClick={onConfig} />
          <ActionBtn icon={Zap} label="测试" onClick={onTest} />
          {!isDefault && model.enabled && model.kind !== 'image' && model.kind !== 'video' && (
            <ActionBtn icon={Star} label="设为默认" onClick={onSetDefault} />
          )}
        </div>
        <button
          type="button"
          title="删除"
          onClick={onDelete}
          className="rounded-md p-1 text-stone-400 opacity-0 transition group-hover:opacity-100 hover:bg-red-100 hover:text-red-600"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
