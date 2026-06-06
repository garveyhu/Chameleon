/** ProviderCard —— 单个供应商的现代卡片。
 *
 * 品牌化图标 + 凭证状态 + 模型数 + base_url + 启用/配置/删除。
 * 网关（kind=gateway）用 primary 描边 + 徽标突出为"统一上游"中枢。
 */

import { Boxes, Pencil, Trash2 } from 'lucide-react';

import { ProviderAvatar } from '@/core/components/common/provider-avatar';
import { Badge } from '@/core/components/ui/badge';
import { StatusBadge } from '@/core/components/ui/status-badge';
import { Switch } from '@/core/components/ui/switch';
import { cn } from '@/core/lib/cn';
import type { ProviderItem } from '@/system/providers/types/provider';

const KIND_LABEL: Record<string, string> = {
  llm: 'LLM',
  embedding: '向量',
  gateway: '网关',
  dify: 'Dify',
  fastgpt: 'FastGPT',
  coze: 'Coze',
  comfyui: '生图',
};

interface Props {
  provider: ProviderItem;
  modelCount: number;
  onConfig: () => void;
  onDelete: () => void;
  onToggle: (enabled: boolean) => void;
}

export const ProviderCard = ({
  provider: p,
  modelCount,
  onConfig,
  onDelete,
  onToggle,
}: Props) => {
  const gateway = p.kind === 'gateway';

  return (
    <div
      className={cn(
        'group flex flex-col rounded-xl border bg-[var(--color-paper)] p-5 transition hover:-translate-y-0.5 hover:shadow-pop',
        gateway
          ? 'border-primary-200 ring-1 ring-primary-100'
          : 'border-stone-200 hover:border-stone-300',
        !p.enabled && 'opacity-65',
      )}
    >
      <div className="flex items-start gap-3">
        <ProviderAvatar code={p.code} size="md" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-medium text-stone-900">{p.name}</div>
          <div className="truncate font-mono text-[11px] text-stone-400">{p.code}</div>
        </div>
        <Badge variant={gateway ? 'primary' : undefined} className="shrink-0">
          {KIND_LABEL[p.kind] || p.kind}
        </Badge>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {p.has_api_key ? (
          <StatusBadge tone="success">凭证已配</StatusBadge>
        ) : (
          <StatusBadge tone="warning">凭证未配</StatusBadge>
        )}
        <span className="inline-flex items-center gap-1 rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] font-medium text-stone-500">
          <Boxes className="h-3 w-3" />
          {modelCount} 模型
        </span>
      </div>

      <div
        className="mt-2 truncate font-mono text-[11px] text-stone-500"
        title={p.base_url || ''}
      >
        {p.base_url || '默认地址'}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-stone-100 pt-3">
        <div className="flex items-center gap-2">
          <Switch checked={p.enabled} onCheckedChange={onToggle} />
          <span className="text-[11px] text-stone-400">{p.enabled ? '已启用' : '已停用'}</span>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            title="配置"
            onClick={onConfig}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-stone-600 transition hover:bg-stone-100 hover:text-stone-900"
          >
            <Pencil className="h-3.5 w-3.5" /> 配置
          </button>
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
    </div>
  );
};
