/** 配额展示 + 编辑 卡片 —— members 页顶部 + 独立 dashboard 复用 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Gauge, RotateCcw, Save } from 'lucide-react';
import { useEffect, useState } from 'react';

import { SectionCard } from '@/core/components/table';
import { Button } from '@/core/components/ui/button';
import { Input } from '@/core/components/ui/input';
import { Label } from '@/core/components/ui/label';
import { cn } from '@/core/lib/cn';
import { formatDateTime } from '@/core/lib/format';
import { toast } from '@/core/lib/toast';
import type { EntityId } from '@/core/types/api';
import { workspaceApi } from '@/system/workspaces/services/workspace';
import type {
  QuotaItem,
  UpdateQuotaPayload,
} from '@/system/workspaces/types/workspace';

interface Props {
  workspaceId: EntityId;
}

export const QuotaCard: React.FC<Props> = ({ workspaceId }) => {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['workspace-quota', workspaceId],
    queryFn: () => workspaceApi.getQuota(workspaceId),
    enabled: !!workspaceId,
  });

  const [tokenLimit, setTokenLimit] = useState('');
  const [requestLimit, setRequestLimit] = useState('');

  useEffect(() => {
    if (q.data) {
      setTokenLimit(
        q.data.token_quota_monthly !== null
          ? String(q.data.token_quota_monthly)
          : '',
      );
      setRequestLimit(
        q.data.request_quota_daily !== null
          ? String(q.data.request_quota_daily)
          : '',
      );
    }
  }, [q.data]);

  const saveMut = useMutation({
    mutationFn: (p: UpdateQuotaPayload) =>
      workspaceApi.updateQuota(workspaceId, p),
    onSuccess: () => {
      toast.success('配额已更新');
      qc.invalidateQueries({ queryKey: ['workspace-quota', workspaceId] });
    },
    onError: (e: unknown) => {
      toast.error((e as { message?: string })?.message || '更新失败');
    },
  });

  const resetMut = useMutation({
    mutationFn: () =>
      workspaceApi.updateQuota(workspaceId, {
        token_quota_monthly: q.data?.token_quota_monthly ?? null,
        request_quota_daily: q.data?.request_quota_daily ?? null,
        reset_used: true,
      }),
    onSuccess: () => {
      toast.success('已重置 used');
      qc.invalidateQueries({ queryKey: ['workspace-quota', workspaceId] });
    },
  });

  if (q.isLoading || !q.data) {
    return (
      <SectionCard>
        <div className="py-8 text-center text-[12px] text-stone-400">
          加载配额…
        </div>
      </SectionCard>
    );
  }

  const handleSave = () => {
    saveMut.mutate({
      token_quota_monthly: tokenLimit.trim() ? Number(tokenLimit) : null,
      request_quota_daily: requestLimit.trim() ? Number(requestLimit) : null,
      reset_used: false,
    });
  };

  return (
    <SectionCard>
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-1.5 text-[13px] font-medium text-stone-900">
            <Gauge className="h-3.5 w-3.5 text-stone-500" />
            workspace 配额
          </h2>
          <p className="mt-0.5 text-[11px] text-stone-500">
            上次重置：{formatDateTime(q.data.reset_at)} · 跨期自动 reset
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => resetMut.mutate()}
          disabled={resetMut.isPending}
        >
          <RotateCcw className="mr-1 h-3 w-3" /> 重置 used
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3">
        <UsageBar
          title="本月 token"
          used={q.data.token_used_current_month}
          limit={q.data.token_quota_monthly}
        />
        <UsageBar
          title="今日请求"
          used={q.data.request_used_today}
          limit={q.data.request_quota_daily}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-stone-200/70 pt-3">
        <div className="space-y-1.5">
          <Label className="text-[11px]">
            月 token 上限
            <span className="ml-1 text-stone-400">（空=无限）</span>
          </Label>
          <Input
            type="number"
            value={tokenLimit}
            onChange={e => setTokenLimit(e.target.value)}
            placeholder="例 1000000"
            min={0}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-[11px]">
            日请求上限
            <span className="ml-1 text-stone-400">（空=无限）</span>
          </Label>
          <Input
            type="number"
            value={requestLimit}
            onChange={e => setRequestLimit(e.target.value)}
            placeholder="例 5000"
            min={0}
          />
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <Button
          size="sm"
          variant="primary"
          onClick={handleSave}
          disabled={saveMut.isPending}
        >
          <Save className="mr-1 h-3 w-3" />
          {saveMut.isPending ? '保存中…' : '保存上限'}
        </Button>
      </div>
    </SectionCard>
  );
};

// ── 使用率条 ─────────────────────────────────────────


interface UsageBarProps {
  title: string;
  used: number;
  limit: number | null;
}

const UsageBar: React.FC<UsageBarProps> = ({ title, used, limit }) => {
  const pct = limit && limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const exhausted = limit !== null && used >= limit;
  return (
    <div className="rounded-md border border-stone-200/70 bg-stone-50/40 px-3 py-2.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-stone-500">{title}</span>
        <span
          className={cn(
            'font-mono text-[12px] tnum',
            exhausted ? 'text-rose-600' : 'text-stone-800',
          )}
        >
          {used.toLocaleString()}
          {limit !== null ? ` / ${limit.toLocaleString()}` : ' / ∞'}
        </span>
      </div>
      {limit !== null && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-stone-200/70">
          <div
            className={cn(
              'h-full transition-all',
              exhausted
                ? 'bg-rose-500'
                : pct > 80
                  ? 'bg-amber-500'
                  : 'bg-primary-500',
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
};
